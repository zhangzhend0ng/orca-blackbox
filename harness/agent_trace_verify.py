"""Shared read-only frame and trusted trace validation; no GUI/model calls."""
from decimal import Decimal, InvalidOperation
import hashlib
import re
import struct
from .agent_verify import _fields, _identity, _int, _require
from .script_verify import _InvalidEvidence, _check_cancel, _json
_REQUEST = {"schema_version", "run_id", "seq", "method", "arguments", "observation_id"}
_RESPONSE = {"schema_version", "run_id", "seq", "tool", "is_error", "error_code", "observation", "finished"}
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")

_REPORT = {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd",
           "started_at_ns", "finished_at_ns", "status", "calls", "clicks"}
_PROCESS = {"schema_version", "run_id", "case_id", "backend", "pid", "started_at_ns",
            "finished_at_ns", "exit_code", "active_processes", "job_assigned", "forced_termination", "cancel_reason"}

def _number(value):
    _require(type(value) is str and len(value) <= 64 and _NUMBER.fullmatch(value), "gcode_invalid_number")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise _InvalidEvidence("gcode_invalid_number") from exc
    _require(number.is_finite() and abs(number) <= Decimal("10000000"), "gcode_number_range")
    return number


def _frame(raw, width, height, cancelled):
    _check_cancel(cancelled)
    _require(len(raw) >= 54 and raw[:2] == b"BM", "frame_magic")
    size, reserved, offset = struct.unpack_from("<III", raw, 2)
    dib, w, h, planes, bits, compression, image_size = struct.unpack_from("<IiiHHII", raw, 14)
    _require(reserved == 0 and offset == 54 and dib == 40 and w == width and abs(h) == height
             and 313 <= w <= 8192 and 68 <= abs(h) <= 8192 and w * abs(h) <= 16_000_000
             and planes == 1 and bits == 32 and compression == 0 and image_size == w * abs(h) * 4
             and size == len(raw) == 54 + image_size, "frame_structure")
    pixels = memoryview(raw)[54:]
    minima, maxima = [255] * 3, [0] * 3
    for offset in range(0, len(pixels), 65536):
        _check_cancel(cancelled)
        chunk = pixels[offset:offset + 65536]
        for channel in range(3):
            minima[channel] = min(minima[channel], min(chunk[channel::4]))
            maxima[channel] = max(maxima[channel], max(chunk[channel::4]))
        if minima != maxima:
            return
    raise _InvalidEvidence("frame_uniform")


def verify_trace(snapshot, report, read, references, cancelled, *, project_initial=None):
    lines = read("trace.ndjson", 1024 * 1024)
    _require(lines.endswith(b"\n") and len(lines.splitlines()) == report["calls"], "trace_count_or_truncation")
    trace = [_json(line) for line in lines.splitlines()]
    project = project_initial is not None
    if project:
        _require(snapshot.contract.case_id == "m3g_export_3mf" and snapshot.contract.contract_version == "ai-project-1", "unsupported_contract")
        boundaries = [i for i, pair in enumerate(trace, 1) if type(pair) is dict and type(pair.get("request")) is dict
                      and pair["request"].get("method") == "reopen_project"]
        _require(len(boundaries) == 1, "reopen_count")
        boundary = boundaries[0]
    previous_id, window_identity, last_time, clicks = None, None, report["started_at_ns"], 0
    operations, receipt_bounds = [], {}
    for seq, pair in enumerate(trace, 1):
        _check_cancel(cancelled)
        _fields(pair, {"request", "response"}, "trace_schema")
        request, response = pair["request"], pair["response"]
        _fields(request, _REQUEST, "request_schema")
        _fields(response, _RESPONSE, "response_schema")
        for item in (request, response):
            _identity(item, snapshot.run_id)
            _require(_int(item["seq"], 1, 12) and item["seq"] == seq, "trace_sequence")
        method = request["method"]
        _require(method in (("observe", "click", "finish", "edit", "slice", "export_gcode", "save_project", "reopen_project") if project else ("observe", "click", "finish", "edit", "slice", "export_gcode"))
                 and response["tool"] == method and response["is_error"] is False
                 and response["error_code"] is None and request["observation_id"] == previous_id
                 and type(response["finished"]) is bool and response["finished"] == (method == "finish")
                 and (seq != 1 or method == "observe")
                 and (method != "finish" or seq == len(trace)), "tool_lineage_or_order")
        args = request["arguments"]
        if method in ("click", "edit"):
            _fields(args, {"x", "y", "text"} if method == "edit" else {"x", "y"}, "action_arguments")
            _require(_int(args["x"], 0, 8191) and _int(args["y"], 0, 8191), "action_coordinates")
            if method == "click":
                _require(40 <= args["x"] <= 312 and 31 <= args["y"] <= 67, "click_outside_tab_band")
                clicks += 1
            else:
                _require(_number(args["text"]) == Decimal("0.24"), "edit_requested_value")
        else:
            _require(type(args) is dict and not args, "action_arguments")
        observation = response["observation"]
        _fields(observation, {"id", "frames", "image", "window"}, "observation_schema")
        oid = observation["id"]
        _require(type(oid) is str and oid == f"{snapshot.run_id}_{seq:04d}", "observation_identity")
        previous_id = oid
        window = observation["window"]
        _fields(window, {"hwnd", "pid", "width", "height", "dpi"}, "window_schema")
        expected = project_initial if project and seq < boundary else {"pid": report["app_pid"], "hwnd": report["hwnd"]}
        _require(all(type(window[k]) is int for k in window) and window["hwnd"] == expected["hwnd"]
                 and window["pid"] == expected["pid"] and window["dpi"] == 96
                 and _int(window["width"], 313, 8192) and _int(window["height"], 68, 8192)
                 and (window_identity is None or (all(window[k] == window_identity[k] for k in ("width", "height", "dpi")) if project else window == window_identity)), "window_identity")
        window_identity = dict(window)
        if method in ("click", "edit"):
            _require(args["x"] < window["width"] and args["y"] < window["height"], "action_outside_window")
        frames, times = observation["frames"], []
        _require(type(frames) is list and len(frames) == 2, "frame_pair_missing")
        prior_time = last_time
        for index, frame in enumerate(frames):
            _fields(frame, {"path", "sha256", "width", "height", "captured_at_ns"}, "frame_schema")
            name = f"frames/{seq:04d}_{'ab'[index]}.bmp"
            _require(frame["path"] == name and type(frame["width"]) is int and type(frame["height"]) is int
                     and frame["width"] == window["width"] and frame["height"] == window["height"]
                     and _int(frame["captured_at_ns"], prior_time, report["finished_at_ns"]), "frame_identity_or_time")
            raw = read(name, 64 * 1024 * 1024)
            _require(hashlib.sha256(raw).hexdigest() == frame["sha256"], "frame_hash")
            _frame(raw, window["width"], window["height"], cancelled)
            times.append(frame["captured_at_ns"])
            references.append("artifact:" + name)
        _require(times[1] - times[0] >= 1_000_000_000, "frame_pair_interval")
        last_time = times[1]
        image = observation["image"]
        _fields(image, {"path", "sha256", "size_bytes"}, "image_schema")
        name = f"frames/{seq:04d}.png"
        _require(image["path"] == name and _int(image["size_bytes"], 8, 16 * 1024 * 1024), "image_identity")
        raw = read(name, 16 * 1024 * 1024)
        _require(raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) == image["size_bytes"]
                 and hashlib.sha256(raw).hexdigest() == image["sha256"], "image_hash")
        if method in (("edit", "slice", "export_gcode", "save_project", "reopen_project") if project else ("edit", "slice", "export_gcode")):
            operations.append((seq, method, request))
            receipt_bounds[seq] = (prior_time, times[0])
    return trace, operations, receipt_bounds


def read_completion(snapshot, read):
    contract, start = snapshot.contract, snapshot.manifest["started_at_ns"]
    process, report = _json(read("process.json", 65536)), _json(read("agent_report.json", 65536))
    _fields(process, _PROCESS, "process_schema")
    _fields(report, _REPORT, "report_schema")
    for item in (process, report):
        _identity(item, snapshot.run_id)
        _require(item["case_id"] == contract.case_id, "case_identity")
    _require(process["backend"] == "win32_job" and process["job_assigned"] is True
             and process["forced_termination"] is False and process["cancel_reason"] is None
             and _int(process["pid"], 1) and type(process["active_processes"]) is int
             and process["active_processes"] == 0 and type(process["exit_code"]) is int
             and process["exit_code"] == 0 and _int(process["started_at_ns"], start)
             and _int(process["finished_at_ns"], process["started_at_ns"]), "process_not_quiescent")
    _require(report["status"] == "completed" and _int(report["driver_pid"], 1)
             and report["driver_pid"] == process["pid"] and _int(report["app_pid"], 1)
             and report["app_pid"] != report["driver_pid"] and _int(report["hwnd"], 1)
             and _int(report["calls"], 7, 12) and _int(report["clicks"], 0, 6)
             and _int(report["started_at_ns"], process["started_at_ns"])
             and _int(report["finished_at_ns"], report["started_at_ns"], process["finished_at_ns"])
             and report["finished_at_ns"] - report["started_at_ns"] <= 900_000_000_000, "report_identity_or_budget")
    return process, report
