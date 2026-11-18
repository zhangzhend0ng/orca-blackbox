"""Independent read-only canvas trace audit; never queries or drives a GUI."""
import hashlib
import json
import re

from .agent_verify import _require
from .script_verify import _InvalidEvidence, _unique_pairs
from .canvas_approval import resolve_approval
from .canvas_input import bind_canvas, binding_to_json, load_canvas_binding, decide_type
from .native_save_policy import validate_input
from .native_matrix import CANVAS_REPLACE_SCENARIO, CANVAS_SCENARIOS


def _json(raw):
    def invalid(_):
        raise _InvalidEvidence("canvas_json_constant")
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=invalid)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise _InvalidEvidence("canvas_json_invalid") from exc


def _time(value):
    return type(value) is int and value > 0


def verify_canvas_trace(trace, scope, setup, *, run_id, contract_sha256, read_artifact):
    """Recompute authority using hashed raw observations and static approval.

    read_artifact(name, limit) must enforce run ownership, link rejection,
    freshness and cancellation. Names below are verifier-derived, never paths
    selected by a model. Parent verifier still audits all noncanvas evidence.
    """
    try:
        return _verify(trace, scope, setup, run_id, contract_sha256, read_artifact)
    except _InvalidEvidence:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError) as exc:
        raise _InvalidEvidence("canvas_authority_invalid") from exc


def _verify(trace, scope, setup, run_id, contract_sha256, read_artifact):
    _require(type(run_id) is str and re.fullmatch("[0-9a-f]{32}", run_id)
             and type(contract_sha256) is str and re.fullmatch("[0-9a-f]{64}", contract_sha256), "canvas_expected_identity")
    _require(type(scope) is dict and type(setup) is dict and scope.get("scenario") in CANVAS_SCENARIOS,
             "canvas_trial_scope")
    scenario = scope["scenario"]
    replace = scenario == CANVAS_REPLACE_SCENARIO
    for data in (scope, setup):
        _require(data.get("run_id") == run_id and data.get("contract_sha256") == contract_sha256,
                 "canvas_run_contract_mismatch")
    _require(setup.get("pfd_verified") is False and setup.get("internal_numeric_field_verified") is False,
             "canvas_unproven_claim")
    approval = resolve_approval(scope["canvas_approval_profile"],
        diagnostic_sha256=scope["canvas_diagnostic_sha256"], sut_sha256=scope["canvas_sut_sha256"])
    initial = setup["evidence"]
    bound = load_canvas_binding(scope["canvas_binding_json"], run_id=run_id,
        app_pid=scope["app_pid"], process_created=initial["process_created"],
        main_hwnd=scope["hwnd"], approval=approval)
    _require(_json(binding_to_json(bound)) == setup["binding"], "canvas_setup_binding_mismatch")
    rebuilt = bind_canvas(initial, bound.hwnd, approved_class=approval.window_class,
                          diagnostic_id=approval.diagnostic_run_id, approval=approval)
    _require(bound == rebuilt and initial["run_id"] == run_id, "canvas_setup_identity_mismatch")
    _require(type(trace) is list and 1 <= len(trace) <= 40, "canvas_trace_size")
    last_click, canvas_count, edit_count = None, 0, 0
    last_observed = initial["captured_monotonic_ns"]
    for seq, row in enumerate(trace, 1):
        _require(type(row) is dict and row.get("run_id") == run_id
                 and type(row.get("seq")) is int and row["seq"] == seq
                 and "error" in row and type(row.get("dispatched")) is bool, "canvas_trace_identity")
        if row.get("error") is not None or row.get("dispatched") is not True:
            continue  # Parent recovery/fatal audit remains mandatory.
        args, window = row.get("arguments"), row.get("window")
        if replace and row["tool"] == "Shortcut":
            last_click = None
        if row.get("tool") == "Click":
            _require(type(args) is dict and type(window) is dict, "canvas_click_schema")
            validate_input("Click", args, scope["output_path"], scenario)
            _require(all(type(window.get(k)) is int and window[k] == bound.app_pid
                         for k in ("app_pid", "foreground_pid", "target_pid")), "canvas_click_ownership")
            stamp = window.get("click_finished_monotonic_ns")
            _require(_time(stamp), "canvas_click_timestamp")
            last_click = (args["loc"], window.get("target_hwnd"), stamp, args.get("clicks", 1))
        if row.get("tool") != "Type":
            continue
        _require(type(args) is dict and type(window) is dict, "canvas_type_schema")
        validate_input("Type", args, scope["output_path"], scenario)
        name = "canvas_input_" + str(seq) + ".json"
        _require(window.get("observation_file") == name, "canvas_observation_name")
        raw = read_artifact(name, 2_000_000)
        _require(type(raw) is bytes and 1 <= len(raw) <= 2_000_000
                 and hashlib.sha256(raw).hexdigest() == window.get("observation_sha256"), "canvas_observation_hash")
        current = _json(raw)
        _require(type(current) is dict, "canvas_observation_schema")
        captured, finished = current.get("captured_monotonic_ns"), current.get("observation_finished_ns")
        checked = window.get("guard_checked_monotonic_ns")
        _require(all(_time(v) for v in (captured, finished, checked))
                 and last_observed <= captured <= finished <= checked, "canvas_observation_time")
        last_observed = checked
        decision = decide_type("pilot_transform", args["text"], args["loc"], current,
            output_path=scope["output_path"], now_ns=checked, binding=bound)
        _require(all(window.get(k) == v for k, v in decision.items()), "canvas_decision_mismatch")
        target = next(w for w in current["windows"] if w["hwnd"] == decision["target_hwnd"])
        expected = dict(foreground_hwnd=current["foreground_hwnd"], focus_hwnd=current["focus_hwnd"],
            process_created=current["process_created"], captured_monotonic_ns=captured,
            target_class=target["class"], target_title=target.get("title", ""),
            canvas_diagnostic_sha256=approval.diagnostic_sha256, canvas_profile=approval.profile_id,
            pfd_index=target.get("pixel_format", {}).get("index", 0))
        _require(all(window.get(k) == v for k, v in expected.items()), "canvas_compact_evidence_mismatch")
        _require(window.get("pfd_verified") is False and window.get("internal_numeric_field_verified") is False,
                 "canvas_unproven_claim")
        _require(current["run_id"] == run_id and current["app_pid"] == bound.app_pid
                 and current["process_created"] == bound.process_created and current["main_hwnd"] == bound.main_hwnd
                 and current["thread_desktop"] == bound.desktop and current["session_id"] == bound.session_id
                 and next(w["rect"] for w in current["windows"] if w["hwnd"] == bound.main_hwnd) == list(bound.main_rect),
                 "canvas_current_identity")
        if decision["route"] == "canvas_numeric":
            _require(args.get("clear", False) is False and args.get("press_enter", False) is replace
                     and args.get("caret_position", "idle") == "idle", "canvas_narrow_options")
            _require(last_click is not None and last_click[0] == args["loc"] and last_click[1] == bound.hwnd
                     and 0 <= checked-last_click[2] <= 30_000_000_000
                     and (not replace or last_click[3] == 1), "canvas_recent_click_required")
            _require(window.get("input_backend") == ("focused_keys_no_click" if replace else None),
                     "canvas_input_backend")
            last_click = None
            canvas_count += 1
        else:
            edit_count += 1
    _require(canvas_count > 0, "canvas_path_not_exercised")
    return dict(canvas_numeric_count=canvas_count, native_edit_count=edit_count,
                approval_profile=approval.profile_id, diagnostic_sha256=approval.diagnostic_sha256,
                pfd_verified=False, internal_numeric_field_verified=False)
