"""Read-only audit of an extracted ai-layer-1 guest run and its host CLI evidence.

This audits trusted local receipts, not cryptographic provenance or firmware/print
quality. It never launches GUI, VM, relay, a model, or writes evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import stat
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.agent_layer_verify import _PROCESS, _RECEIPT, _frame, analyze_gcode, request_digest, verify_layer
from harness.agent_model import _action, _parse_output
from harness.agent_protocol import LAYER_FIXTURE_SHA256, validate_request
from harness.run_contract import validate_contract
from harness.run_evidence import _METADATA, _id, _json as canonical_json
from harness.run_verdict import aggregate_result, contract_digest
from harness.script_verify import _json, _read

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SUMMARY = {"provider", "model", "usage", "dollar_cost", "action", "proxy_source",
            "input_image_sha256", "prompt_sha256", "cli_executable_sha256", "started_at_ns", "finished_at_ns"}
_HOST = {"schema_version", "run_id", "case_id", "model_source", "finished", "release_eligible", "dollar_cost",
         "started_at_ns", "finished_at_ns", "actions", "model_calls"}
_TOKENS = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens"}
_FAULTS = {"wrong_parameter", "missing_reslice", "export_collision"}
_SENTINEL = b"orca-v3-export-collision-v1\n"


class AuditError(ValueError):
    """Stable operator code; never include an untrusted payload or path."""


def _need(condition, code):
    if not condition:
        raise AuditError(code)


def _integer(value, low=0, high=10**20):
    return type(value) is int and low <= value <= high


def _fields(value, names, code):
    _need(type(value) is dict and set(value) == names, code)


def _root(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        info = item.lstat()
        _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
              "root_link_rejected")
    _need(path.is_dir(), "root_not_directory")
    return path


def _read_at(root, name, limit, start=0):
    # Names come from fixed constants or separately validated call identifiers.
    _need(type(name) is str and all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) and x not in (".", "..")
                                   for x in name.split("/")), "unsafe_evidence_path")
    return _read(root, name, start, limit, lambda: False)


def _data(root, name, start=0):
    return _json(_read_at(root, name, 65536, start))


def _events(root, manifest, *, execution_status="completed", has_verification=True):
    raw = _read_at(root, "events.ndjson", 256 * 1024, manifest["started_at_ns"])
    lines = raw.splitlines()
    _need(raw.endswith(b"\n") and 2 <= len(lines) <= 64, "events_incomplete")
    previous, previous_time, cleanup = "", None, {}
    messages = []
    for seq, line in enumerate(lines):
        event = _json(line)
        _fields(event, {"timestamp", "level", "message", "context", "sequence", "previous_sha256"}, "event_schema")
        _fields(event["context"], {"run_id", "step_id", "status", "evidence"}, "event_context")
        _need(canonical_json(event) == line and type(event["sequence"]) is int and event["sequence"] == seq
              and event["previous_sha256"] == previous and event["context"]["run_id"] == manifest["run_id"]
              and event["level"] == "INFO", "event_chain_invalid")
        stamp = datetime.fromisoformat(event["timestamp"])
        _need(stamp.tzinfo is not None and (previous_time is None or stamp >= previous_time), "event_time")
        previous_time, previous = stamp, hashlib.sha256(line).hexdigest()
        name, context = event["message"], event["context"]
        messages.append((name, context["status"], context["step_id"]))
        if name == "cleanup_started":
            key = _id(context["step_id"])
            _need(key not in cleanup, "duplicate_cleanup")
            cleanup[key] = False
        elif name == "cleanup_finished":
            key = context["step_id"]
            _need(key in cleanup and cleanup[key] is False and context["status"] == "confirmed", "cleanup_event_unconfirmed")
            cleanup[key] = True
    expected = [("runtime_started", "guest_agent", None), ("execution_finished", execution_status, None)]
    if has_verification:
        expected += [("verification_started", None, None), ("verification_finished", "completed", None)]
    for operation in range(2 if has_verification else 1):
        expected += [("cleanup_started", None, f"operation_{operation}"),
                     ("cleanup_finished", "confirmed", f"operation_{operation}")]
    expected += [("runtime_finished", execution_status, None)]
    _need(messages == expected and cleanup and all(cleanup.values()), "events_not_completed")
    return {"count": len(lines), "last_sha256": previous}


def _one_call(host, index):
    parent = host / f"model_{index:04d}"
    _root(parent)
    children = list(islice(parent.iterdir(), 4))
    _need(len(children) == 1 and re.fullmatch(r"call-[0-9a-f]{32}", children[0].name), "model_call_directory")
    _root(children[0])
    return f"model_{index:04d}/{children[0].name}"


def _model_lineage(host, trace, run_id, case_id, start):
    report = _data(host, "host_run.json", start)
    _fields(report, _HOST, "host_schema")
    count = report["model_calls"]
    _need(report["schema_version"] == 1 and type(report["schema_version"]) is int
          and report["run_id"] == run_id and report["case_id"] == case_id and report["model_source"] == "codex_cli"
          and report["finished"] is True and report["release_eligible"] is False and report["dollar_cost"] is None
          and _integer(count, 1, 8) and len(trace) == count + 1 and type(report["actions"]) is list
          and len(report["actions"]) == count and _integer(report["started_at_ns"], start)
          and _integer(report["finished_at_ns"], report["started_at_ns"])
          and report["finished_at_ns"] - report["started_at_ns"] <= 600_000_000_000, "host_identity_or_budget")
    children = list(islice(host.iterdir(), 65))
    _need(len(children) <= 64 and {p.name for p in children if p.name.startswith("model_")} ==
          {f"model_{i:04d}" for i in range(1, count + 1)}, "extra_model_calls")
    usage, usage_known, cli_hashes, models = {}, True, set(), set()
    for index in range(1, count + 1):
        observation, request = trace[index - 1]["response"]["observation"], trace[index]["request"]
        prefix = _one_call(host, index)
        summary = _data(host, prefix + "/summary.json", start)
        _fields(summary, _SUMMARY, "model_summary_schema")
        parsed, tokens = _parse_output(_read_at(host, prefix + "/stdout.jsonl", 4 * 1024 * 1024, start))
        window = observation["window"]
        action = _action(parsed, observation["id"], window["width"], window["height"], case_id=case_id)
        _need(summary["action"] == action == report["actions"][index - 1] ==
              _data(host, f"action_{index:04d}.json", start), "model_action_mismatch")
        arguments = {k: action[k] for k in (("x", "y", "text") if action["tool"] == "edit" else
                                          ("x", "y") if action["tool"] == "click" else ())}
        _need(action["tool"] == request["method"] and action["observation_id"] == request["observation_id"]
              and request["arguments"] == arguments, "guest_action_mismatch")
        image = _read_at(host, f"observation_{index:04d}.png", 16 * 1024 * 1024, start)
        _need(summary["provider"] == "codex" and summary["dollar_cost"] is None
              and summary["proxy_source"] in ("system", "environment", "none")
              and all(type(summary[key]) is str and _HASH.fullmatch(summary[key]) for key in
                      ("input_image_sha256", "prompt_sha256", "cli_executable_sha256"))
              and hashlib.sha256(image).hexdigest() == summary["input_image_sha256"] == observation["image"]["sha256"]
              and _integer(summary["started_at_ns"], max(report["started_at_ns"], observation["frames"][-1]["captured_at_ns"]))
              and _integer(summary["finished_at_ns"], summary["started_at_ns"], report["finished_at_ns"])
              and summary["finished_at_ns"] <= trace[index]["response"]["observation"]["frames"][0]["captured_at_ns"],
              "model_image_identity_or_time")
        _need(summary["model"] is None or (type(summary["model"]) is str and
              re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", summary["model"])), "model_name")
        _need(summary["usage"] == tokens, "model_usage_mismatch")
        if tokens is None:
            usage_known = False
        else:
            _need(type(tokens) is dict and {"input_tokens", "output_tokens"} <= set(tokens) <= _TOKENS
                  and all(_integer(x, 0, 10**9) for x in tokens.values()), "model_usage_schema")
            for key, value in tokens.items():
                usage[key] = usage.get(key, 0) + value
        cli_hashes.add(summary["cli_executable_sha256"])
        models.add(summary["model"])
    _need(len(cli_hashes) == len(models) == 1, "mixed_model_versions")
    return {"verified": True, "calls": count, "usage": usage if usage_known else None,
            "usage_known": usage_known, "dollar_cost": None, "model": models.pop(),
            "cli_executable_sha256": cli_hashes.pop(), "prompt_hash_recomputed": False,
            "tool_calls": len(trace), "host_elapsed_s": (report["finished_at_ns"] - report["started_at_ns"]) / 10**9}


def _probe_lineage(host, artifacts, manifest, ready, process, fault):
    """Fixed experiment actions are separately attributed, never counted as AI."""
    start, run_id, source = manifest["started_at_ns"], manifest["run_id"], "fault_probe_" + fault
    probe, report = _data(host, "fault_probe.json", start), _data(host, "host_run.json", start)
    _fields(probe, {"schema_version", "run_id", "case_id", "fault", "source", "ai_trial", "model_inference",
        "expected_release_verdict", "release_eligible", "observed_release_verdict", "cleanup_confirmed",
        "disposition", "host_finished", "host_error_type"}, "fault_probe_schema")
    _need(type(report) is dict and _HOST - {"actions", "model_calls"} <= set(report) <=
          _HOST | {"cancel_request_written", "error_type", "bridge_close_error", "cancel_error_type"}, "fault_host_schema")
    _need(type(probe) is dict and type(report) is dict and probe.get("run_id") == report.get("run_id") == run_id
          and probe.get("case_id") == report.get("case_id") == manifest["case_id"] and probe.get("fault") == fault
          and probe.get("source") == report.get("model_source") == source and probe.get("ai_trial") is False
          and probe.get("model_inference") is False and probe.get("release_eligible") is False
          and type(probe["schema_version"]) is type(report["schema_version"]) is int
          and probe["schema_version"] == report["schema_version"] == 1
          and type(report["finished"]) is bool and probe["host_finished"] is report["finished"]
          and report["release_eligible"] is False and report["dollar_cost"] is None
          and _integer(report["started_at_ns"], start) and _integer(report["finished_at_ns"], report["started_at_ns"])
          and report["finished_at_ns"] - report["started_at_ns"] <= 600_000_000_000
          and probe.get("expected_release_verdict") == "NON_GREEN", "fault_source_identity")
    raw = _read_at(artifacts, "trace.ndjson", 1024 * 1024, start)
    trace = [_json(x) for x in raw.splitlines()]
    _need(raw.endswith(b"\n") and 6 <= len(trace) <= 7, "fault_trace_count")
    sequence = ["observe", "slice", "export_gcode", "edit",
                "observe" if fault == "missing_reslice" else "slice", "export_gcode", "finish"]
    prior, last_time = None, start
    for seq, pair in enumerate(trace, 1):
        _fields(pair, {"request", "response"}, "fault_trace_schema")
        req, res = pair["request"], pair["response"]
        validate_request(req, run_id=run_id, expected_seq=seq, observation_id=prior, case_id=manifest["case_id"])
        _need(req["method"] == sequence[seq - 1], "fault_sequence_not_hit")
        _fields(res, {"schema_version", "run_id", "seq", "tool", "is_error", "error_code", "observation", "finished"}, "fault_response_schema")
        _need(type(res["schema_version"]) is int and res["schema_version"] == 1 and res["run_id"] == run_id
              and type(res["seq"]) is int and res["seq"] == seq and res["tool"] == req["method"]
              and type(res["is_error"]) is bool and type(res["finished"]) is bool, "fault_response_identity")
        if res["is_error"]:
            _need(seq == len(trace) == 6 and req["method"] == "export_gcode" and res["finished"] is False
                  and res["error_code"] == ("export_exists" if fault == "export_collision" else "export_not_ready")
                  and fault != "wrong_parameter" and res["observation"] is None, "unrelated_fault_error")
            continue
        _need(res["error_code"] is None and res["finished"] == (req["method"] == "finish"), "fault_response_status")
        obs = res["observation"]
        _fields(obs, {"id", "window", "frames", "image"}, "fault_observation_schema")
        _need(type(obs["window"]) is dict and all(type(v) is int for v in obs["window"].values())
              and obs["id"] == f"{run_id}_{seq:04d}" and obs["window"] == {"hwnd": ready["hwnd"], "pid": ready["app_pid"],
              "width": 1920, "height": 1032, "dpi": 96}, "fault_window_identity")
        prior = obs["id"]
        _need(type(obs["frames"]) is list and len(obs["frames"]) == 2, "fault_frame_pair")
        times = []
        for index, frame in enumerate(obs["frames"]):
            name = f"frames/{seq:04d}_{'ab'[index]}.bmp"
            _fields(frame, {"path", "sha256", "width", "height", "captured_at_ns"}, "fault_frame_schema")
            _need(frame["path"] == name and frame["width"] == 1920 and frame["height"] == 1032
                  and _integer(frame["captured_at_ns"], last_time, process["finished_at_ns"]), "fault_frame_identity")
            pixels = _read_at(artifacts, name, 64 * 1024 * 1024, start)
            _need(hashlib.sha256(pixels).hexdigest() == frame["sha256"], "fault_frame_hash")
            _frame(pixels, 1920, 1032, lambda: False)
            times.append(frame["captured_at_ns"])
        _need(times[1] - times[0] >= 1_000_000_000, "fault_frame_interval")
        last_time = times[-1]
        image = obs["image"]
        _fields(image, {"path", "sha256", "size_bytes"}, "fault_image_schema")
        _need(image["path"] == f"frames/{seq:04d}.png", "fault_image_path")
        pixels = _read_at(artifacts, image["path"], 16 * 1024 * 1024, start)
        _need(pixels.startswith(b"\x89PNG\r\n\x1a\n") and len(pixels) == image["size_bytes"]
              and hashlib.sha256(pixels).hexdigest() == image["sha256"], "fault_image_hash")
    _need((len(trace) == 7 and trace[-1]["response"]["finished"] is True) or trace[-1]["response"]["is_error"] is True,
          "fault_trace_incomplete")
    count = len(trace) - 1
    children = list(islice(host.iterdir(), 65))
    _need(len(children) <= 64 and {p.name for p in children if p.name.startswith("model_")} ==
          {f"model_{i:04d}" for i in range(1, count + 1)}, "extra_probe_calls")
    actions = []
    for i in range(1, count + 1):
        parent = _root(host / f"model_{i:04d}")
        _need([p.name for p in islice(parent.iterdir(), 3)] == ["summary.json"], "probe_not_fixed_source")
        record = _data(host, f"model_{i:04d}/summary.json", start)
        _fields(record, {"source", "model_inference", "ai_trial", "image_sha256", "observation_id", "action", "created_at_ns"}, "probe_summary_schema")
        observation, request = trace[i - 1]["response"]["observation"], trace[i]["request"]
        action = _action(record["action"], observation["id"], 1920, 1032, case_id=manifest["case_id"])
        expected = {"tool": request["method"], "observation_id": request["observation_id"], "x": None, "y": None, "text": None}
        if expected["tool"] == "edit":
            expected.update(x=298, y=794 if fault == "wrong_parameter" else 764, text="0.24")
            _need(request["arguments"] == {k: expected[k] for k in ("x", "y", "text")}, "fault_edit_not_hit")
        following = trace[i]["response"]["observation"]
        upper_time = following["frames"][0]["captured_at_ns"] if following is not None else process["finished_at_ns"]
        _need(record["source"] == source and record["model_inference"] is False and record["ai_trial"] is False
              and record["observation_id"] == observation["id"] and action == expected == _data(host, f"action_{i:04d}.json", start)
              and record["image_sha256"] == observation["image"]["sha256"] == hashlib.sha256(
                  _read_at(host, f"observation_{i:04d}.png", 16 * 1024 * 1024, start)).hexdigest()
              and _integer(record["created_at_ns"], observation["frames"][-1]["captured_at_ns"],
                           upper_time), "probe_action_lineage")
        actions.append(action)
    _need(("actions" not in report or report["actions"] == actions) and ("model_calls" not in report or
          (type(report["model_calls"]) is int and report["model_calls"] == count)), "probe_report_actions")
    return trace, {"verified": False, "fixed_action_lineage": True, "model_inference": False,
                   "ai_trial": False, "calls": count, "usage": None, "dollar_cost": None, "tool_calls": len(trace),
                   "host_elapsed_s": (report["finished_at_ns"] - report["started_at_ns"]) / 10**9}


def _fault_receipts(artifacts, manifest, ready, trace):
    start, run_id = manifest["started_at_ns"], manifest["run_id"]
    raw = _read_at(artifacts, "operation_receipts.ndjson", 1024 * 1024, start)
    records = [_json(x) for x in raw.splitlines()]
    successful = [pair for pair in trace if pair["request"]["method"] in ("edit", "slice", "export_gcode")
                  and pair["response"]["is_error"] is False]
    _need(raw.endswith(b"\n") and len(records) == len(successful) + 1, "fault_receipts_missing")
    for record in records:
        _fields(record, _RECEIPT, "fault_receipt_schema")
        _need(type(record["schema_version"]) is int and record["schema_version"] == 1 and record["run_id"] == run_id
              and record["window"] == {"hwnd": ready["hwnd"], "pid": ready["app_pid"]}, "fault_receipt_identity")
    boot = records[0]
    _need(type(boot["seq"]) is int and boot["seq"] == 0 and boot["method"] == "boot" and boot["request_sha256"] is None
          and _integer(boot["started_at_ns"], start) and _integer(boot["finished_at_ns"], boot["started_at_ns"],
              trace[0]["response"]["observation"]["frames"][0]["captured_at_ns"])
          and boot["details"] == {"datadir": "profile", "driver_pid": ready["driver_pid"],
              "fixture_path": "input/fixture.3mf", "fixture_sha256": LAYER_FIXTURE_SHA256}, "fault_boot_receipt")
    exports = 0
    for record, pair in zip(records[1:], successful):
        request, response = pair["request"], pair["response"]
        seq, method = request["seq"], request["method"]
        _need(type(record["seq"]) is int and record["seq"] == seq and record["method"] == method
              and record["request_sha256"] == request_digest(request) and _integer(record["started_at_ns"],
                  trace[seq - 2]["response"]["observation"]["frames"][-1]["captured_at_ns"])
              and _integer(record["finished_at_ns"], record["started_at_ns"],
                  response["observation"]["frames"][0]["captured_at_ns"]), "fault_receipt_lineage")
        details = record["details"]
        if method == "edit":
            _fields(details, {"target_hwnd", "control_class", "before_text", "after_text"}, "fault_edit_receipt")
            _need(_integer(details["target_hwnd"], 1) and details["control_class"] == "Edit"
                  and details["before_text"] in ("0.4", "0.40") and details["after_text"] == "0.24", "fault_edit_receipt")
        elif method == "slice":
            _fields(details, {"button_hwnd", "done_observed"}, "fault_slice_receipt")
            _need(_integer(details["button_hwnd"], 1) and details["done_observed"] is True, "fault_slice_receipt")
        else:
            exports += 1
            _fields(details, {"dialog_hwnd", "edit_hwnd", "path", "sha256", "size_bytes"}, "fault_export_receipt")
            _need(_integer(details["dialog_hwnd"], 1) and _integer(details["edit_hwnd"], 1)
                  and details["path"] == f"exports/{exports:04d}.gcode" and _integer(details["size_bytes"], 1, 64 * 1024 * 1024), "fault_export_receipt")
            content = _read_at(artifacts, details["path"], 64 * 1024 * 1024, start)
            _need(len(content) == details["size_bytes"] and hashlib.sha256(content).hexdigest() == details["sha256"], "fault_export_hash")


def _collision(host, artifacts, manifest, trace):
    start, run_id = manifest["started_at_ns"], manifest["run_id"]
    digest = hashlib.sha256(_SENTINEL).hexdigest()
    request = {"schema_version": 1, "run_id": run_id, "fault": "export_collision", "source": "fault_probe_export_collision",
        "operation": "create_new", "path": "exports/0002.gcode", "content_ascii": _SENTINEL.decode("ascii"),
        "sha256": digest, "size_bytes": len(_SENTINEL)}
    ack = {k: request[k] for k in ("schema_version", "run_id", "fault", "path", "sha256", "size_bytes")}
    ack["created_new"] = True
    raw_request = _read_at(host, "fault_injection_request.json", 4096, start)
    value = _json(raw_request)
    _need(value == request and all(type(value[k]) is type(v) for k, v in request.items()), "collision_request")
    for name in ("fault_injection_ack.json", "fault_injection_accepted.json"):
        value = _data(host, name, start)
        _need(value == ack and all(type(value[k]) is type(v) for k, v in ack.items()), "collision_ack")
    receipt = _data(artifacts, "fault_injection.json", start)
    expected = {**ack, "source": request["source"], "request_sha256": hashlib.sha256(raw_request).hexdigest(),
        "case_id": manifest["case_id"], "contract_sha256": manifest["contract_sha256"], "observation_id": f"{run_id}_0005"}
    _fields(receipt, set(expected) | {"created_at_ns"}, "collision_guest_receipt")
    created = _data(host, "model_0005/summary.json", start)["created_at_ns"]
    _need(all(receipt[k] == v and type(receipt[k]) is type(v) for k, v in expected.items())
          and _integer(receipt["created_at_ns"], trace[4]["response"]["observation"]["frames"][-1]["captured_at_ns"], created)
          and _read_at(artifacts, "exports/0002.gcode", 4096, start) == _SENTINEL
          and trace[-1]["response"]["error_code"] == "export_exists", "collision_not_proven")


def _audit_fault(root, host, artifacts, manifest, verification, output, fault):
    start, run_id = manifest["started_at_ns"], manifest["run_id"]
    result, process, ready = _data(root, "result.json", start), _data(artifacts, "process.json", start), _data(artifacts, "ready.json", start)
    _fields(process, _PROCESS, "fault_process_schema")
    _fields(ready, {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd", "contract_sha256"}, "fault_ready_schema")
    _need(result.get("release_verdict") == "NON_GREEN" and result.get("verified_pass") is False
          and result.get("release_eligible") is False and result.get("cleanup_confirmed") is True
          and result.get("runtime_status") == result.get("execution_status") in ("completed", "failed", "cancelled"), "fault_not_rejected")
    _need(type(process["schema_version"]) is type(ready["schema_version"]) is int and process["schema_version"] == ready["schema_version"] == 1
          and all(_integer(ready[k], 1) for k in ("driver_pid", "app_pid", "hwnd"))
          and process.get("run_id") == ready.get("run_id") == run_id
          and process.get("case_id") == ready.get("case_id") == manifest["case_id"] and process.get("backend") == "win32_job"
          and process.get("job_assigned") is True and type(process.get("active_processes")) is int and process["active_processes"] == 0
          and type(process["forced_termination"]) is bool and type(process["exit_code"]) is int
          and process["cancel_reason"] in (None, "cancelled") and _integer(process["started_at_ns"], start)
          and _integer(process.get("pid"), 1) and process["pid"] == ready.get("driver_pid")
          and _integer(process.get("finished_at_ns"), process["started_at_ns"]) and ready.get("contract_sha256") == manifest["contract_sha256"],
          "fault_job_or_identity_unconfirmed")
    trace, lineage = _probe_lineage(host, artifacts, manifest, ready, process, fault)
    _fault_receipts(artifacts, manifest, ready, trace)
    output["model_lineage"] = lineage
    output["natural_cleanup"] = process.get("exit_code") == 0 and process.get("forced_termination") is False and process.get("cancel_reason") is None
    output["process"] = {k: process[k] for k in ("exit_code", "forced_termination", "cancel_reason", "active_processes")}
    output["guest_elapsed_s"] = (process["finished_at_ns"] - process["started_at_ns"]) / 10**9
    output["events"] = _events(root, manifest, execution_status=result["execution_status"],
                                has_verification=result["execution_status"] == "completed")
    _need(hashlib.sha256(_read_at(artifacts, "input/fixture.3mf", 1024 * 1024, start)).hexdigest() == LAYER_FIXTURE_SHA256,
          "fault_fixture_identity")
    baseline = analyze_gcode(_read_at(artifacts, "exports/0001.gcode", 64 * 1024 * 1024, start), layer_height="0.4")
    if fault == "wrong_parameter":
        target = analyze_gcode(_read_at(artifacts, "exports/0002.gcode", 64 * 1024 * 1024, start),
                               layer_height="0.4", first_layer_height="0.24")
        _need(output["natural_cleanup"] and verification.checks["path"].status == result["checks"]["path"]["status"] == "pass"
              and verification.checks["business"].status == result["checks"]["business"]["status"] == "fail"
              and target["object_tools"] == baseline["object_tools"], "wrong_parameter_not_proven")
        output["exports"] = [baseline, target]
    elif fault == "missing_reslice":
        _need(sum(x["request"]["method"] == "slice" for x in trace) == 1 and
              (trace[-1]["response"]["error_code"] == "export_not_ready" or
               (output["natural_cleanup"] and verification.checks["path"].status != "pass"
                and verification.checks["path"].detail == "operation_order")), "missing_reslice_not_proven")
        output["exports"] = [baseline]
    else:
        _collision(host, artifacts, manifest, trace)
        output["exports"] = [baseline]
    output.update(audit_ok=True, status="EXPECTED_NON_GREEN", fault_source="fault_probe_" + fault,
                  expected_NON_GREEN=True, ai_trial=False, observed_release_verdict="NON_GREEN",
                  tool_rejection=trace[-1]["response"]["error_code"])
    return output


def audit_run(run_dir: Path, host_dir: Path, *, expected_fault=None) -> dict:
    """Fail closed; a rejected/missing run is never an expected-fault success.

    Only the three frozen experiment faults are recognized. Source/SUT/CLI
    binding to a batch plan remains the coordinator's separate verification.
    """
    output = {"schema_version": 1, "audit_ok": False, "status": "NOT_ACCEPTED", "fault_source": None,
              "expected_NON_GREEN": False, "release_eligible": False, "full_verification": False,
              "natural_cleanup": False, "model_lineage": {"verified": False}, "batch_binding_verified": False}
    try:
        _need(expected_fault is None or expected_fault in _FAULTS, "expected_fault_not_registered")
        root, host = _root(run_dir), _root(host_dir)
        manifest = _data(root, "manifest.json")
        _fields(manifest, {"schema_version", "run_id", "case_id", "executor", "started_at", "started_at_ns", "contract_sha256", "metadata"}, "manifest_schema")
        run_id, start = _id(manifest["run_id"]), manifest["started_at_ns"]
        output["run_id"] = run_id
        _need(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and _integer(start, 1)
              and manifest["case_id"] == "m3d_param_reslice" and manifest["executor"] == "agent_mcp"
              and type(manifest["metadata"]) is dict and set(manifest["metadata"]) <= _METADATA
              and all(type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/+ -]{1,256}", value)
                      for value in manifest["metadata"].values())
              and type(manifest["started_at"]) is str and len(manifest["started_at"]) <= 64, "manifest_identity")
        started_at = datetime.fromisoformat(manifest["started_at"])
        _need(started_at.tzinfo is not None and abs(started_at.timestamp() * 10**9 - start) <= 1_000_000,
              "manifest_time")
        raw_contract = _read_at(root, "contract.json", 65536, start)
        contract = validate_contract(_json(raw_contract))
        _need(hashlib.sha256(raw_contract).hexdigest() == manifest["contract_sha256"] == contract_digest(contract), "contract_hash")
        from harness.agent_session import agent_contract
        _need(contract_digest(contract) == contract_digest(agent_contract("m3d_param_reslice")), "unregistered_contract")
        _need(contract.limits.timeout_s == 900 and contract.limits.max_actions == 12
              and contract.limits.max_retries == 0 and contract.limits.max_cost_usd == 0, "unsupported_budget")
        output["contract_sha256"] = manifest["contract_sha256"]
        output["version_metadata"] = {k: manifest["metadata"].get(k) for k in
            ("repository_commit", "sut_sha256", "executor_version", "checker_version")}
        artifacts = _root(root / "artifacts")
        snapshot = SimpleNamespace(contract=contract, artifact_dir=artifacts, run_id=run_id, manifest=manifest)
        verification = verify_layer(snapshot)
        output["checks"] = {k: {"status": v.status, "detail": v.detail} for k, v in verification.checks.items()}
        output["full_verification"] = verification.evidence_complete and verification.execution_compliant and all(
            verification.checks[k].status == "pass" for k in ("path", "business"))
        if expected_fault is not None:
            return _audit_fault(root, host, artifacts, manifest, verification, output, expected_fault)
        _need(output["full_verification"], "full_verification_rejected")
        result = _data(root, "result.json", start)
        _need(result.get("execution_status") == result.get("runtime_status") == "completed"
              and result.get("cleanup_confirmed") is True and result.get("release_eligible") is False
              and result.get("gui_execution_requested") is True, "runtime_not_completed")
        expected = aggregate_result(contract, "completed", verification.checks,
                                    evidence_complete=True, execution_compliant=True).to_dict()
        expected["mode"] = "agent_shadow"  # Trusted runtime's guest_agent mode.
        _need(all(result.get(k) == v and type(result.get(k)) is type(v) for k, v in expected.items()), "persisted_verdict_mismatch")
        process = _data(artifacts, "process.json", start)
        report = _data(artifacts, "agent_report.json", start)
        ready = _data(artifacts, "ready.json", start)
        _fields(ready, {"schema_version", "run_id", "case_id", "driver_pid", "app_pid", "hwnd", "contract_sha256"}, "ready_schema")
        _need(type(ready["schema_version"]) is int and ready["schema_version"] == 1 and ready["run_id"] == run_id
              and ready["case_id"] == contract.case_id and ready["contract_sha256"] == manifest["contract_sha256"]
              and all(type(ready[k]) is int and ready[k] == report[k] for k in ("driver_pid", "app_pid", "hwnd")), "ready_identity")
        output["natural_cleanup"] = (process["exit_code"] == 0 and process["forced_termination"] is False
            and process["cancel_reason"] is None and process["active_processes"] == 0 and process["job_assigned"] is True)
        _need(output["natural_cleanup"], "natural_cleanup_unconfirmed")
        output["process"] = {k: process[k] for k in ("exit_code", "forced_termination", "cancel_reason", "active_processes")}
        output["guest_elapsed_s"] = (process["finished_at_ns"] - process["started_at_ns"]) / 10**9
        output["events"] = _events(root, manifest)
        trace = [_json(x) for x in _read_at(artifacts, "trace.ndjson", 1024 * 1024, start).splitlines()]
        output["model_lineage"] = _model_lineage(host, trace, run_id, contract.case_id, start)
        output["exports"] = [analyze_gcode(_read_at(artifacts, f"exports/{i:04d}.gcode", 64 * 1024 * 1024, start),
                                           layer_height=height) for i, height in ((1, "0.4"), (2, "0.24"))]
        output.update(audit_ok=True, status="SHADOW", fault_source=None)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError) as exc:
        output["error"] = str(exc) if isinstance(exc, AuditError) else "invalid_or_unavailable_evidence"
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--host-dir", type=Path, required=True)
    parser.add_argument("--expected-fault", choices=sorted(_FAULTS))
    args = parser.parse_args(argv)
    result = audit_run(args.run_dir, args.host_dir, expected_fault=args.expected_fault)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["audit_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
