"""Independent oracle for the fixed AI tab-state loop; never reads model prose.

Only the guest's trusted trace/captures and Job receipt are evidence. Selected
tab colors establish visible selection, not page contents or slicing correctness.
"""
from __future__ import annotations

import hashlib
import re
import struct
import threading

from .run_verdict import CheckResult
from .runtime_ports import CleanupOutcome, Done, Pending, VerificationOutcome
from .script_verify import _InvalidEvidence, _check_cancel, _json, _read

_REQUEST = {"schema_version", "run_id", "seq", "method", "arguments", "observation_id"}
_RESPONSE = {"schema_version", "run_id", "seq", "tool", "is_error", "error_code", "observation", "finished"}
_REPORT = {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd",
           "started_at_ns", "finished_at_ns", "status", "calls", "clicks"}
_PROCESS = {"schema_version", "run_id", "case_id", "backend", "pid", "started_at_ns",
            "finished_at_ns", "exit_code", "active_processes", "job_assigned",
            "forced_termination", "cancel_reason"}
# Approved dark-theme, 96-DPI client-space probes from harness/anchors.py.
_PREPARE, _PREVIEW = (108, 49), (244, 49)
_SELECTED, _UNSELECTED, _COLOR_TOL = (136, 150, 0), (70, 68, 59), 60


def _require(condition, code):
    if not condition:
        raise _InvalidEvidence(code)


def _fields(value, names, code):
    _require(type(value) is dict and set(value) == names, code)


def _int(value, low=0, high=2**63 - 1):
    return type(value) is int and low <= value <= high


def _identity(value, run_id):
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1
             and value["run_id"] == run_id, "evidence_identity")


def _frame_state(raw, width, height, cancelled):
    """Decode a standard 32-bit BI_RGB BMP, including signed top-down height."""
    _check_cancel(cancelled)
    _require(len(raw) >= 54 and raw[:2] == b"BM", "frame_magic")
    size, reserved, offset = struct.unpack_from("<III", raw, 2)
    dib, w, h, planes, bits, compression, image_size = struct.unpack_from("<IiiHHII", raw, 14)
    _require(reserved == 0 and offset == 54 and dib == 40 and w == width and abs(h) == height
             and 313 <= w <= 8192 and 68 <= abs(h) <= 8192 and w * abs(h) <= 16_000_000
             and planes == 1 and bits == 32 and compression == 0
             and image_size == w * abs(h) * 4 and size == len(raw) == 54 + image_size,
             "frame_structure")
    def sample(point):
        x, y = point
        row = y if h < 0 else height - 1 - y
        at = 54 + 4 * (row * width + x)
        return tuple(raw[at:at + 3])
    def near(actual, expected):
        return sum(abs(a - b) for a, b in zip(actual, expected)) < _COLOR_TOL
    prepare, preview = sample(_PREPARE), sample(_PREVIEW)
    if near(prepare, _SELECTED) and near(preview, _UNSELECTED):
        return "prepare"
    if near(preview, _SELECTED) and near(prepare, _UNSELECTED):
        return "preview"
    raise _InvalidEvidence("tab_state_not_mutually_exclusive")


def verify_agent(snapshot, *, cancelled=lambda: False) -> VerificationOutcome:
    """Verify guest-captured states and exact call lineage for ai-tabs-1 only."""
    references = []
    try:
        contract = snapshot.contract
        _require(contract.case_id == "m1_minimal_loop" and contract.contract_version == "ai-tabs-1"
                 and contract.executor == "agent_mcp"
                 and tuple(s.id for s in contract.steps) == ("boot", "preview", "prepare", "close")
                 and set(contract.required_checks) == {"path", "business"}, "unsupported_contract")
        root, start = snapshot.artifact_dir, snapshot.manifest["started_at_ns"]
        read = lambda name, limit: _read(root, name, start, limit, cancelled)
        process = _json(read("process.json", 65536))
        _fields(process, _PROCESS, "process_schema")
        _identity(process, snapshot.run_id)
        _require(process["case_id"] == contract.case_id and process["backend"] == "win32_job"
                 and process["job_assigned"] is True and process["forced_termination"] is False
                 and process["cancel_reason"] is None and _int(process["pid"], 1)
                 and type(process["active_processes"]) is int and process["active_processes"] == 0
                 and type(process["exit_code"]) is int and process["exit_code"] == 0
                 and _int(process["started_at_ns"], start)
                 and _int(process["finished_at_ns"], process["started_at_ns"]), "process_not_quiescent")
        report = _json(read("agent_report.json", 65536))
        _fields(report, _REPORT, "report_schema")
        _identity(report, snapshot.run_id)
        _require(report["case_id"] == contract.case_id and report["status"] == "completed"
                 and _int(report["driver_pid"], 1) and report["driver_pid"] == process["pid"]
                 and _int(report["app_pid"], 1) and report["app_pid"] != report["driver_pid"]
                 and _int(report["hwnd"], 1) and _int(report["calls"], 4, 12)
                 and _int(report["clicks"], 2, 6)
                 and _int(report["started_at_ns"], process["started_at_ns"])
                 and _int(report["finished_at_ns"], report["started_at_ns"], process["finished_at_ns"])
                 and report["finished_at_ns"] - report["started_at_ns"] <= 900_000_000_000,
                 "report_identity_or_budget")
        trace_raw = read("trace.ndjson", 1024 * 1024)
        _require(trace_raw.endswith(b"\n"), "trace_truncated")
        lines = trace_raw.splitlines()
        _require(len(lines) == report["calls"], "trace_call_count")
        previous_id, last_time, window_identity = None, report["started_at_ns"], None
        seen_ids, stage, clicks, last_state = set(), 0, 0, None
        for seq, line in enumerate(lines, 1):
            _check_cancel(cancelled)
            item = _json(line)
            _fields(item, {"request", "response"}, "trace_schema")
            request, response = item["request"], item["response"]
            _fields(request, _REQUEST, "request_schema")
            _fields(response, _RESPONSE, "response_schema")
            _identity(request, snapshot.run_id)
            _identity(response, snapshot.run_id)
            _require(_int(request["seq"], 1, 12) and request["seq"] == seq
                     and _int(response["seq"], 1, 12) and response["seq"] == seq,
                     "trace_sequence")
            method, arguments = request["method"], request["arguments"]
            _require(method in ("observe", "click", "finish") and response["tool"] == method
                     and response["is_error"] is False and response["error_code"] is None
                     and request["observation_id"] == previous_id, "tool_or_observation_lineage")
            _require(type(response["finished"]) is bool and response["finished"] == (method == "finish"),
                     "finish_flag")
            if method == "click":
                _fields(arguments, {"x", "y"}, "click_arguments")
                _require(_int(arguments["x"], 40, 312) and _int(arguments["y"], 31, 67), "click_outside_tabs")
                clicks += 1
                _require(clicks <= 6, "click_budget")
            else:
                _require(type(arguments) is dict and not arguments, "unexpected_arguments")
            _require((seq != 1 or method == "observe")
                     and (method != "finish" or seq == len(lines)), "call_order")
            observation = response["observation"]
            _fields(observation, {"id", "frames", "image", "window"}, "observation_schema")
            oid = observation["id"]
            _require(type(oid) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", oid)
                     and oid not in seen_ids, "observation_id_reused")
            seen_ids.add(oid)
            previous_id = oid
            window = observation["window"]
            _fields(window, {"hwnd", "pid", "width", "height", "dpi"}, "window_schema")
            _require(all(type(window[k]) is int for k in window)
                     and window["hwnd"] == report["hwnd"] and window["pid"] == report["app_pid"]
                     and window["dpi"] == 96 and _int(window["width"], 313, 8192)
                     and _int(window["height"], 68, 8192), "window_identity_or_geometry")
            _require(window_identity is None or window_identity == window, "window_changed")
            window_identity = dict(window)
            frames = observation["frames"]
            _require(type(frames) is list and len(frames) == 2, "stable_pair_missing")
            states, times = [], []
            for index, frame in enumerate(frames):
                _fields(frame, {"path", "sha256", "width", "height", "captured_at_ns"}, "frame_schema")
                name = f"frames/{seq:04d}_{'ab'[index]}.bmp"
                _require(frame["path"] == name and frame["width"] == window["width"]
                         and type(frame["width"]) is int and type(frame["height"]) is int
                         and frame["height"] == window["height"]
                         and _int(frame["captured_at_ns"], last_time, report["finished_at_ns"]), "frame_identity_or_time")
                raw = read(name, 64 * 1024 * 1024)
                digest = hashlib.sha256(raw).hexdigest()
                _require(frame["sha256"] == digest, "frame_hash")
                states.append(_frame_state(raw, window["width"], window["height"], cancelled))
                times.append(frame["captured_at_ns"])
                references.append("artifact:" + name + ":sha256:" + digest)
            _require(times[1] - times[0] >= 1_000_000_000 and states[0] == states[1], "unstable_tab_pair")
            last_time = times[1]
            image = observation["image"]
            _fields(image, {"path", "sha256", "size_bytes"}, "image_schema")
            name = f"frames/{seq:04d}.png"
            _require(image["path"] == name and _int(image["size_bytes"], 8, 16 * 1024 * 1024), "image_identity")
            png = read(name, 16 * 1024 * 1024)
            _require(png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) == image["size_bytes"]
                     and hashlib.sha256(png).hexdigest() == image["sha256"], "image_hash_or_size")
            state = states[0]
            if seq == 1:
                _require(state == "prepare", "initial_state")
            elif method == "click":
                if stage == 0 and state == "preview":
                    stage = 1
                elif stage == 1 and state == "prepare":
                    stage = 2
                elif state != last_state:
                    raise _InvalidEvidence("unexpected_tab_transition")
            else:
                _require(state == last_state, "unattributed_state_change")
            if method == "finish":
                _require(stage == 2 and state == "prepare", "finish_before_loop_complete")
            last_state = state
        _require(stage == 2 and request["method"] == "finish" and clicks == report["clicks"], "loop_or_click_count")
        refs = tuple(references + ["artifact:trace.ndjson", "artifact:agent_report.json", "artifact:process.json"])
        return VerificationOutcome({name: CheckResult("pass", "visible tab selection loop only", refs)
                                    for name in ("path", "business")}, True, True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, struct.error) as exc:
        code = str(exc) if isinstance(exc, _InvalidEvidence) else "agent_evidence_unavailable"
        return VerificationOutcome({name: CheckResult("unknown", code) for name in ("path", "business")}, False, False)


class _Cleanup:
    def __init__(self, handle):
        self.handle = handle

    def poll(self):
        return Pending() if self.handle.worker.is_alive() else Done(CleanupOutcome(True))


class _VerifierHandle:
    def __init__(self, snapshot):
        self.cancelled = threading.Event()
        self.result, self.error = None, None
        def work():
            try:
                self.result = verify_agent(snapshot, cancelled=self.cancelled.is_set)
            except BaseException as exc:
                self.error = exc
        self.worker = threading.Thread(target=work, name="agent-tabs-verifier", daemon=True)
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


class AgentTabVerifier:
    synthetic = False

    def start(self, snapshot):
        return _VerifierHandle(snapshot)
