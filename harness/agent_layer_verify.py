"""Independent ai-layer-1 oracle over trusted GUI trace and actual gcode moves.

This verifies the generated object's regular-layer Z schedule and positive XY/E
motion, not firmware execution or arbitrary geometric/slicing correctness.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import struct
import threading

from . import gcode_check
from .agent_protocol import LAYER_FIXTURE_SHA256
from .agent_trace_verify import _frame, _number, _PROCESS, _REPORT, read_completion, verify_trace
from .agent_verify import _fields, _identity, _int, _require
from .run_verdict import CheckResult
from .runtime_ports import CleanupOutcome, Done, Pending, VerificationOutcome
from .script_verify import _InvalidEvidence, _check_cancel, _json, _read

_REQUEST = {"schema_version", "run_id", "seq", "method", "arguments", "observation_id"}
_RESPONSE = {"schema_version", "run_id", "seq", "tool", "is_error", "error_code", "observation", "finished"}
_RECEIPT = {"schema_version", "run_id", "seq", "method", "request_sha256", "started_at_ns", "finished_at_ns", "window", "details"}
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")
_LABEL = re.compile(r"; (printing|stop printing) object (.{1,512}) id:(\d{1,24}) copy (\d{1,12})\Z")
_TOL = Decimal("0.001")


def request_digest(request):
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def analyze_gcode(raw: bytes, *, layer_height: str, first_layer_height="0.4", cancelled=lambda: False) -> dict:
    """Inspect supported U1 object moves, excluding purge/tower/retraction/Z-hop.

    Global G90/G91, M82/M83 and G92 are tracked. Object extrusion must occur at
    a known Z and known E mode; unsupported arc/body modes are not guessed.
    """
    _require(type(raw) is bytes and 1 <= len(raw) <= 64 * 1024 * 1024, "gcode_size")
    wanted, first = _number(layer_height), _number(first_layer_height)
    for key, expected in (("layer_height", wanted), ("first_layer_height", first)):
        echoes = gcode_check.config_value_all(raw, key)
        _require(bool(echoes) and all(_number(x) == expected for x in echoes), "gcode_" + key + "_mismatch")
    text = raw.decode("utf-8", errors="strict")
    lines = text.splitlines()
    _require(len(lines) <= 1_000_000, "gcode_line_limit")
    for start, end in (("; EXECUTABLE_BLOCK_START", "; EXECUTABLE_BLOCK_END"),
                       ("; CONFIG_BLOCK_START", "; CONFIG_BLOCK_END")):
        _require(lines.count(start) == lines.count(end) == 1 and lines.index(start) < lines.index(end),
                 "gcode_incomplete_blocks")
    lo, hi = lines.index("; EXECUTABLE_BLOCK_START"), lines.index("; EXECUTABLE_BLOCK_END")
    # GCode.cpp emits these labels around the same object-instance body when
    # gcode_label_objects is enabled and EXCLUDE_OBJECT is disabled. The label
    # identifies scope only; layer values still come exclusively from moves.
    exclude_mode = any(line.startswith("EXCLUDE_OBJECT_") and not line.startswith("EXCLUDE_OBJECT_DEFINE")
                       for line in lines[lo + 1:hi])
    position = {k: None for k in "XYZE"}
    absolute_xyz, relative_e, active, objects = None, None, None, set()
    z_layers, moves, active_tool, object_tools, tower = [], 0, None, set(), False
    for i, line in enumerate(lines[lo + 1:hi]):
        if i % 256 == 0:
            _check_cancel(cancelled)
        if line in ("; WIPE_TOWER_START", "; WIPE_TOWER_END"):
            _require(active is None and tower == (line == "; WIPE_TOWER_END"), "gcode_tower_scope")
            tower = line == "; WIPE_TOWER_START"
        if not exclude_mode and line.startswith(("; printing object", "; stop printing object", "; start printing object")):
            label = _LABEL.fullmatch(line)
            _require(label is not None, "gcode_object_label")
            direction, name, object_id, copy_id = label.groups()
            identity = (name, object_id, copy_id)
            if direction == "printing":
                _require(active is None and not tower, "gcode_object_start")
                active = identity
                objects.add(identity)
            else:
                _require(active == identity, "gcode_object_end")
                active = None
            continue
        command = line.split(";", 1)[0].strip()
        if not command:
            continue
        if command.startswith("EXCLUDE_OBJECT_START NAME="):
            name = command.split("NAME=", 1)[1]
            _require(active is None and not tower and 1 <= len(name) <= 512, "gcode_object_start")
            active = name
            objects.add(name)
            continue
        if command.startswith("EXCLUDE_OBJECT_END NAME="):
            _require(active == command.split("NAME=", 1)[1], "gcode_object_end")
            active = None
            continue
        opcode, *words = command.split()
        # Fixed U1/mm scope. Never carry coordinates across a mode we cannot
        # interpret: changing units/origins could otherwise fake a Z schedule.
        _require(opcode not in ("G20", "G10", "G11", "G50", "G51", "G52", "G53",
                                "G54", "G55", "G56", "G57", "G58", "G59", "G68", "G69",
                                "M200", "M206") and not opcode.startswith("G92."), "unsupported_coordinate_mode")
        if opcode == "G21":
            _require(not words, "unsupported_coordinate_mode")
            continue
        if opcode in ("G90", "G91"):
            _require(not words, "unsupported_coordinate_mode")
            absolute_xyz = opcode == "G90"
            continue
        if opcode in ("M82", "M83"):
            relative_e = opcode == "M83"
            continue
        if re.fullmatch(r"T\d+", opcode):
            _require(not words, "unknown_tool_selection")
            active_tool = int(opcode[1:])
            position["E"] = None  # Absolute E needs a new explicit baseline after a tool switch.
            continue
        if opcode not in ("G0", "G1", "G92"):
            if opcode in ("G2", "G3"):
                # The generator uses non-extruding spiral Z-hop. Do not infer
                # arc geometry; require a later straight move to establish XYZ.
                arc_parameters = set()
                for word in words:
                    _require(len(word) > 1 and word[0] in "XYZIJKRPF" and word[0] not in arc_parameters,
                             "unsupported_arc_motion")
                    arc_parameters.add(word[0])
                    _number(word[1:])
                for axis in "XYZ":
                    position[axis] = None
            elif opcode == "G28":
                _require(active is None, "unsupported_object_motion")
                # Startup homing must not leave stale known coordinates.
                position = {k: None for k in "XYZE"}
            elif opcode.startswith("G"):
                _require(opcode in ("G4", "G17"), "unsupported_coordinate_mode")
            continue
        values = {}
        for word in words:
            _require(len(word) > 1 and word[0] in "XYZEF" and word[0] not in values, "unsupported_motion_parameter")
            values[word[0]] = _number(word[1:])
        if opcode == "G92":
            _require(values and not any(axis in values for axis in "XYZ") and "F" not in values,
                     "unsupported_coordinate_reset")
            for axis in position:
                if axis in values:
                    position[axis] = values[axis]
            continue
        old = dict(position)
        for axis in "XYZ":
            if axis in values:
                _require(absolute_xyz is not None, "unknown_xyz_mode")
                position[axis] = values[axis] if absolute_xyz else (
                    None if old[axis] is None else old[axis] + values[axis])
        delta_e = Decimal(0)
        if "E" in values:
            _require(relative_e is not None, "unknown_extrusion_mode")
            if relative_e:
                delta_e = values["E"]
                position["E"] = None if old["E"] is None else old["E"] + values["E"]
            else:
                _require(old["E"] is not None, "unknown_absolute_extrusion_baseline")
                delta_e = values["E"] - old["E"]
                position["E"] = values["E"]
        moving_xy = any(axis in values and (old[axis] is None or position[axis] != old[axis]) for axis in "XY")
        if active is not None and moving_xy and delta_e > 0:
            _require(active_tool is not None, "unknown_object_tool")
            object_tools.add(active_tool)
            _require(len(object_tools) == 1, "gcode_multiple_object_tools")
            _require(all(old[axis] is not None and position[axis] is not None for axis in "XY"), "unknown_object_xy")
            z = position["Z"]
            _require(z is not None and z > 0, "unknown_object_z")
            if not z_layers or abs(z - z_layers[-1]) > _TOL:
                _require(not z_layers or z > z_layers[-1], "gcode_object_z_not_monotonic")
                z_layers.append(z)
            moves += 1
    _require(active is None and not tower and len(objects) == 1 and moves >= 2 and len(z_layers) >= 2, "gcode_missing_object_extrusion")
    _require(abs(z_layers[0] - first) <= _TOL, "gcode_first_actual_layer_mismatch")
    _require(all(abs(b - a - wanted) <= _TOL for a, b in zip(z_layers, z_layers[1:])), "gcode_actual_layer_step_mismatch")
    # The frozen fixture is a 27mm cube; allow one layer of slicer boundary rounding.
    _require(Decimal(27) - wanted <= z_layers[-1] <= Decimal(27) + wanted, "gcode_fixture_height_mismatch")
    return {"layer_height": str(wanted), "first_layer_height": str(first),
            "layer_count": len(z_layers), "first_z": str(z_layers[0]), "last_z": str(z_layers[-1]),
            "positive_xy_e_moves": moves, "object_tools": sorted(object_tools), "sha256": hashlib.sha256(raw).hexdigest()}


def verify_layer(snapshot, *, cancelled=lambda: False) -> VerificationOutcome:
    references, path_checked = [], False
    try:
        contract = snapshot.contract
        _require(contract.case_id == "m3d_param_reslice" and contract.contract_version == "ai-layer-1"
                 and contract.executor == "agent_mcp" and tuple(s.id for s in contract.steps) ==
                 ("boot", "baseline", "edit", "reslice", "close")
                 and set(contract.required_checks) == {"path", "business"}, "unsupported_contract")
        root, start = snapshot.artifact_dir, snapshot.manifest["started_at_ns"]
        read = lambda name, limit: _read(root, name, start, limit, cancelled)
        process, report = read_completion(snapshot, read)
        trace, operations, receipt_bounds = verify_trace(snapshot, report, read, references, cancelled)
        clicks = sum(x["request"]["method"] == "click" for x in trace)
        _require(trace[-1]["request"]["method"] == "finish" and clicks == report["clicks"]
                 and [x[1] for x in operations] == ["slice", "export_gcode", "edit", "slice", "export_gcode"], "operation_order")
        receipts_raw = read("operation_receipts.ndjson", 1024 * 1024)
        _require(receipts_raw.endswith(b"\n"), "receipts_truncated")
        receipts = [_json(line) for line in receipts_raw.splitlines()]
        _require(len(receipts) == 6, "receipt_count")
        for receipt in receipts:
            _fields(receipt, _RECEIPT, "receipt_schema")
            _identity(receipt, snapshot.run_id)
            _fields(receipt["window"], {"hwnd", "pid"}, "receipt_window_schema")
            _require(receipt["window"] == {"hwnd": report["hwnd"], "pid": report["app_pid"]}, "receipt_window_identity")
        boot = receipts[0]
        _require(type(boot["seq"]) is int and boot["seq"] == 0 and boot["method"] == "boot"
                 and boot["request_sha256"] is None and _int(boot["started_at_ns"], report["started_at_ns"])
                 and _int(boot["finished_at_ns"], boot["started_at_ns"], trace[0]["response"]["observation"]["frames"][0]["captured_at_ns"]), "boot_receipt")
        _fields(boot["details"], {"fixture_path", "fixture_sha256", "datadir", "driver_pid"}, "boot_details")
        _require(boot["details"] == {"fixture_path": "input/fixture.3mf", "fixture_sha256": LAYER_FIXTURE_SHA256,
                                     "datadir": "profile", "driver_pid": report["driver_pid"]}, "fixture_identity")
        fixture = read("input/fixture.3mf", 1024 * 1024)
        _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "fixture_hash")
        exports = []
        for receipt, (seq, method, request) in zip(receipts[1:], operations):
            lower, upper = receipt_bounds[seq]
            _require(_int(receipt["seq"], 1, 12) and receipt["seq"] == seq and receipt["method"] == method
                     and receipt["request_sha256"] == request_digest(request)
                     and _int(receipt["started_at_ns"], lower)
                     and _int(receipt["finished_at_ns"], receipt["started_at_ns"], upper), "receipt_lineage_or_time")
            details = receipt["details"]
            if method == "edit":
                _fields(details, {"target_hwnd", "control_class", "before_text", "after_text"}, "edit_receipt")
                _require(_int(details["target_hwnd"], 1) and details["control_class"] == "Edit"
                         and _number(details["before_text"]) == Decimal("0.4")
                         and _number(details["after_text"]) == Decimal("0.24"), "edit_control_or_value")
            elif method == "slice":
                _fields(details, {"button_hwnd", "done_observed"}, "slice_receipt")
                _require(_int(details["button_hwnd"], 1) and details["done_observed"] is True, "slice_control_or_wait")
            else:
                _fields(details, {"dialog_hwnd", "edit_hwnd", "path", "sha256", "size_bytes"}, "export_receipt")
                name = f"exports/{len(exports) + 1:04d}.gcode"
                _require(_int(details["dialog_hwnd"], 1) and _int(details["edit_hwnd"], 1)
                         and details["path"] == name and _int(details["size_bytes"], 1, 64 * 1024 * 1024), "export_dialog_or_identity")
                raw = read(name, 64 * 1024 * 1024)
                _require(len(raw) == details["size_bytes"] and hashlib.sha256(raw).hexdigest() == details["sha256"], "export_hash")
                exports.append(raw)
                references.append("artifact:" + name + ":sha256:" + details["sha256"])
        references += ["artifact:trace.ndjson", "artifact:operation_receipts.ndjson", "artifact:process.json", "artifact:input/fixture.3mf"]
        path_checked = True
        baseline = analyze_gcode(exports[0], layer_height="0.4", cancelled=cancelled)
        target = analyze_gcode(exports[1], layer_height="0.24", cancelled=cancelled)
        _require(target["object_tools"] == baseline["object_tools"], "gcode_object_tool_changed")
        _require(target["layer_count"] > baseline["layer_count"] and target["sha256"] != baseline["sha256"], "reslice_did_not_change_object_layers")
        refs = tuple(references)
        return VerificationOutcome({"path": CheckResult("pass", "GUI slice/export/edit/reslice/export observed", refs),
            "business": CheckResult("pass", f"object Z layers {baseline['layer_count']}x0.4 -> {target['layer_count']}x0.24; first=0.4", refs)}, True, True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, struct.error) as exc:
        code = str(exc) if isinstance(exc, _InvalidEvidence) else "layer_evidence_unavailable"
        business_status = "unknown" if not path_checked or code.startswith(("unsupported", "unknown", "verification_cancelled")) else "fail"
        refs = tuple(references)
        return VerificationOutcome({"path": CheckResult("pass" if path_checked else "unknown", code, refs),
                                    "business": CheckResult(business_status, code, refs)}, False, path_checked)


class _Cleanup:
    def __init__(self, handle):
        self.handle = handle

    def poll(self):
        return Pending() if self.handle.worker.is_alive() else Done(CleanupOutcome(True))


class _Handle:
    def __init__(self, snapshot, check=None):
        check = verify_layer if check is None else check
        self.cancelled = threading.Event()
        self.result, self.error = None, None
        def work():
            try:
                self.result = check(snapshot, cancelled=self.cancelled.is_set)
            except BaseException as exc:
                self.error = exc
        self.worker = threading.Thread(target=work, name="agent-layer-verifier", daemon=True)
        self.worker.start()

    def poll(self):
        if self.worker.is_alive():
            return Pending()
        if self.error is not None:
            raise self.error
        return Done(VerificationOutcome({}, False, False) if self.cancelled.is_set() else self.result)

    def cancel(self, reason):
        self.cancelled.set()

    def start_cleanup(self):
        return _Cleanup(self)


class AgentLayerVerifier:
    synthetic = False

    def start(self, snapshot):
        return _Handle(snapshot)
