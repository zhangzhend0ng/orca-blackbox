"""Independent layer schedule challenges; no GUI, model, or relay."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import threading

import pytest

from harness.agent_layer_verify import AgentLayerVerifier, analyze_gcode, request_digest, verify_layer
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.run_contract import validate_contract
from harness.runtime_ports import Done, Pending


def gcode(layer="0.4", first="0.4", *, e_mode="M83", objects=True, positive=True, echo=None):
    lines = ["; EXECUTABLE_BLOCK_START", "G90", e_mode, "T0", "G92 E0", "G1 X0 Y0 Z0"]
    z, step, n = Decimal(first), Decimal(layer), 0
    while z < Decimal(27) + step:
        n += 1
        # Tower and hop moves must not count as model layers.
        lines += ["G91", "G1 Z1.5", "G90", f"G1 X5 Y5 Z{z}", "G1 X10 E2", "G92 E0"]
        if objects:
            lines += ["EXCLUDE_OBJECT_START NAME=cube", f";Z:{z}", f"G1 X{20 + n % 2} Y20 E{1 if positive else 0}",
                      "G1 E-0.2", "G1 E0.2", "EXCLUDE_OBJECT_END NAME=cube"]
        z += step
    lines += ["; EXECUTABLE_BLOCK_END", "; CONFIG_BLOCK_START",
              f"; layer_height = {echo or layer}", f"; first_layer_height = {first}", "; CONFIG_BLOCK_END", ""]
    return "\n".join(lines).encode()


def test_physical_object_layer_schedule_distinguishes_baseline_and_target():
    a = analyze_gcode(gcode(), layer_height="0.4")
    b = analyze_gcode(gcode("0.24"), layer_height="0.24")
    assert a["layer_count"] == 68 and b["layer_count"] == 112
    assert a["first_z"] == b["first_z"] == "0.4"
    assert a["last_z"] == "27.2" and b["last_z"] == "27.04"


@pytest.mark.parametrize("mode", ["M82", "M83"])
def test_absolute_and_relative_extrusion_with_g92_are_supported(mode):
    assert analyze_gcode(gcode("0.24", e_mode=mode), layer_height="0.24")["layer_count"] == 112


def test_object_extrusion_must_use_one_explicitly_selected_tool():
    raw = gcode("0.24").replace(b";Z:0.64", b"T1\n;Z:0.64", 1)
    with pytest.raises(ValueError, match="multiple_object_tools"):
        analyze_gcode(raw, layer_height="0.24")
    with pytest.raises(ValueError, match="unknown_object_tool"):
        analyze_gcode(gcode("0.24").replace(b"T0\n", b"", 1), layer_height="0.24")


def test_nonobject_tools_do_not_count_as_object_materials():
    raw = gcode("0.24").replace(b"G1 X10 E2", b"T1\nG1 X10 E2\nT0")
    raw = raw.replace(b"; EXECUTABLE_BLOCK_END", b"T999\n; EXECUTABLE_BLOCK_END")
    assert analyze_gcode(raw, layer_height="0.24")["object_tools"] == [0]


def test_echo_only_and_comment_only_edits_do_not_change_real_layers():
    fake = gcode(echo="0.24").replace(b";Z:0.8", b";Z:0.64")
    with pytest.raises(ValueError, match="actual_layer_step"):
        analyze_gcode(fake, layer_height="0.24")


@pytest.mark.parametrize("raw,reason", [(gcode(), "layer_height_mismatch"),
    (gcode("0.24", "0.24"), "first_layer_height_mismatch"),
    (gcode("0.24", objects=False), "missing_object_extrusion"),
    (gcode("0.24", positive=False), "missing_object_extrusion"),
    (gcode("0.24").replace(b"G1 X21 Y20 E1", b"G1 E1").replace(b"G1 X20 Y20 E1", b"G1 E1"), "missing_object_extrusion"),
    (gcode("0.24").replace(b"; CONFIG_BLOCK_END", b""), "incomplete_blocks"),
    (gcode("0.24").replace(b"EXCLUDE_OBJECT_END NAME=cube", b"EXCLUDE_OBJECT_END NAME=other", 1), "object_end")],
    ids=["old-output", "wrong-first", "prime-only", "no-positive-e", "pure-e", "truncated", "object-end"])
def test_wrong_first_layer_old_output_prime_only_pure_e_and_truncation_fail(raw, reason):
    with pytest.raises(ValueError, match=reason):
        analyze_gcode(raw, layer_height="0.24")


def test_conflicting_config_echo_is_rejected():
    raw = gcode("0.24") + b"; layer_height = 0.4\n"
    with pytest.raises(ValueError, match="layer_height_mismatch"):
        analyze_gcode(raw, layer_height="0.24")


def test_nonmonotonic_object_extrusion_is_rejected():
    raw = gcode("0.24").replace(b"G1 X5 Y5 Z0.88", b"G1 X5 Y5 Z0.2")
    with pytest.raises(ValueError, match="not_monotonic"):
        analyze_gcode(raw, layer_height="0.24")


def test_cancel_checks_cover_parser_loop():
    with pytest.raises(ValueError, match="cancelled"):
        analyze_gcode(gcode("0.24"), layer_height="0.24", cancelled=lambda: True)


@pytest.mark.parametrize("command", ["G20", "G52 Z0", "G54", "G92 Z0.4", "M200 D1.75"])
def test_uninterpreted_units_and_origin_modes_cannot_forge_physical_z(command):
    raw = gcode("0.24").replace(b"G90\nM83", command.encode() + b"\nG90\nM83", 1)
    with pytest.raises(ValueError, match="unsupported_coordinate"):
        analyze_gcode(raw, layer_height="0.24")


@pytest.mark.parametrize("command", ["G28", "G2 X0 Y0", "G3 X0 Y0"])
def test_outside_object_motion_invalidates_position_until_reestablished(command):
    raw = gcode("0.24").replace(b"EXCLUDE_OBJECT_START NAME=cube", command.encode() + b"\nEXCLUDE_OBJECT_START NAME=cube", 1)
    with pytest.raises(ValueError, match="unknown_object"):
        analyze_gcode(raw, layer_height="0.24")


def frame():
    width, height = 400, 100
    pixels = b"\x20\x20\x20\xff" + b"\x50\x50\x50\xff" * (width * height - 1)
    return (b"BM" + struct.pack("<III", 54 + len(pixels), 0, 54)
            + struct.pack("<IiiHHIIIIII", 40, width, -height, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels)


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def persist(snapshot, trace, receipts):
    for name, rows in (("trace.ndjson", trace), ("operation_receipts.ndjson", receipts)):
        (snapshot.artifact_dir / name).write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    contract = validate_contract({"schema_version": 1, "case_id": "m3d_param_reslice",
        "contract_version": "ai-layer-1", "executor": "agent_mcp", "required_checks": ["path", "business"],
        "steps": [{"id": x, "goal": x} for x in ("boot", "baseline", "edit", "reslice", "close")],
        "limits": {"timeout_s": 900, "max_actions": 12, "max_retries": 0, "max_cost_usd": 0}})
    snapshot = SimpleNamespace(artifact_dir=tmp_path, run_id="run1", contract=contract,
                               manifest={"started_at_ns": 1_000_000_000})
    for name in ("frames", "input", "exports"):
        (tmp_path / name).mkdir()
    fixture = Path(__file__).resolve().parents[1] / LAYER_FIXTURE
    raw_fixture = fixture.read_bytes()
    assert hashlib.sha256(raw_fixture).hexdigest() == LAYER_FIXTURE_SHA256
    (tmp_path / "input/fixture.3mf").write_bytes(raw_fixture)
    for index, height in enumerate(("0.4", "0.24"), 1):
        (tmp_path / f"exports/{index:04d}.gcode").write_bytes(gcode(height))
    report = {"schema_version": 1, "run_id": "run1", "case_id": contract.case_id, "driver_pid": 100,
        "app_pid": 200, "hwnd": 300, "started_at_ns": 3_000_000_000, "finished_at_ns": 90_000_000_000,
        "status": "completed", "calls": 7, "clicks": 0}
    process = {"schema_version": 1, "run_id": "run1", "case_id": contract.case_id, "pid": 100,
        "backend": "win32_job", "started_at_ns": 2_000_000_000, "finished_at_ns": 91_000_000_000,
        "exit_code": 0, "active_processes": 0, "job_assigned": True, "forced_termination": False, "cancel_reason": None}
    write_json(tmp_path / "agent_report.json", report)
    write_json(tmp_path / "process.json", process)
    receipts = [{"schema_version": 1, "run_id": "run1", "seq": 0, "method": "boot", "request_sha256": None,
        "started_at_ns": 3_000_000_000, "finished_at_ns": 4_000_000_000, "window": {"hwnd": 300, "pid": 200},
        "details": {"fixture_path": "input/fixture.3mf", "fixture_sha256": LAYER_FIXTURE_SHA256,
                    "datadir": "profile", "driver_pid": 100}}]
    trace, export_index = [], 0
    methods = ("observe", "slice", "export_gcode", "edit", "slice", "export_gcode", "finish")
    for seq, method in enumerate(methods, 1):
        request = {"schema_version": 1, "run_id": "run1", "seq": seq, "method": method,
            "arguments": {"x": 250, "y": 90, "text": "0.24"} if method == "edit" else {},
            "observation_id": None if seq == 1 else f"run1_{seq - 1:04d}"}
        frames = []
        for index, letter in enumerate("ab"):
            name, raw = f"frames/{seq:04d}_{letter}.bmp", frame()
            (tmp_path / name).write_bytes(raw)
            frames.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "width": 400, "height": 100,
                           "captured_at_ns": seq * 10_000_000_000 + index * 1_000_000_000})
        png, name = b"\x89PNG\r\n\x1a\nFAKE", f"frames/{seq:04d}.png"
        (tmp_path / name).write_bytes(png)
        response = {"schema_version": 1, "run_id": "run1", "seq": seq, "tool": method, "is_error": False,
            "error_code": None, "finished": method == "finish", "observation": {"id": f"run1_{seq:04d}",
            "frames": frames, "image": {"path": name, "sha256": hashlib.sha256(png).hexdigest(), "size_bytes": len(png)},
            "window": {"hwnd": 300, "pid": 200, "width": 400, "height": 100, "dpi": 96}}}
        trace.append({"request": request, "response": response})
        if method in ("slice", "edit", "export_gcode"):
            if method == "slice":
                details = {"button_hwnd": 500, "done_observed": True}
            elif method == "edit":
                details = {"target_hwnd": 600, "control_class": "Edit", "before_text": "0.40", "after_text": "0.24"}
            else:
                export_index += 1
                path = f"exports/{export_index:04d}.gcode"
                raw = (tmp_path / path).read_bytes()
                details = {"dialog_hwnd": 700, "edit_hwnd": 800, "path": path,
                           "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
            receipts.append({"schema_version": 1, "run_id": "run1", "seq": seq, "method": method,
                "request_sha256": request_digest(request), "started_at_ns": seq * 10_000_000_000 - 2_000_000_000,
                "finished_at_ns": seq * 10_000_000_000 - 1_000_000_000,
                "window": {"hwnd": 300, "pid": 200}, "details": details})
    persist(snapshot, trace, receipts)
    return snapshot, trace, receipts


def test_complete_owned_gui_trace_and_real_gcode_layers_pass(evidence):
    snapshot, *_ = evidence
    result = verify_layer(snapshot)
    assert result.evidence_complete and result.execution_compliant
    assert result.checks["path"].status == result.checks["business"].status == "pass"
    assert "68x0.4 -> 112x0.24" in result.checks["business"].detail


@pytest.mark.parametrize("bad", [gcode(), gcode(echo="0.24"), gcode("0.24", "0.24"),
                                gcode("0.24", objects=False), gcode("0.24")[:-60]])
def test_complete_path_does_not_override_bad_business_output(evidence, bad):
    snapshot, trace, receipts = evidence
    path = snapshot.artifact_dir / "exports/0002.gcode"
    path.write_bytes(bad)
    receipts[-1]["details"].update(sha256=hashlib.sha256(bad).hexdigest(), size_bytes=len(bad))
    persist(snapshot, trace, receipts)
    result = verify_layer(snapshot)
    assert result.checks["path"].status == "pass"
    assert result.checks["business"].status == "fail" and not result.evidence_complete


@pytest.mark.parametrize("field,value", [("request_sha256", "0" * 64), ("seq", 3), ("method", "edit"),
                                      ("window", {"pid": 999, "hwnd": 300}), ("finished_at_ns", 99_000_000_000)])
def test_receipts_are_bound_to_run_request_identity_and_timing(evidence, field, value):
    snapshot, trace, receipts = evidence
    receipts[1][field] = value
    persist(snapshot, trace, receipts)
    assert not verify_layer(snapshot).evidence_complete


def test_wrong_fixture_copy_is_not_accepted(evidence):
    snapshot, *_ = evidence
    (snapshot.artifact_dir / "input/fixture.3mf").write_bytes(b"another fixture")
    assert not verify_layer(snapshot).evidence_complete


def test_export_copy_reuse_requires_actual_new_file_hash(evidence):
    snapshot, *_ = evidence
    (snapshot.artifact_dir / "exports/0002.gcode").write_bytes(gcode())
    assert not verify_layer(snapshot).evidence_complete


def test_baseline_and_target_must_preserve_the_same_object_tool(evidence):
    snapshot, trace, receipts = evidence
    raw = gcode("0.24").replace(b"T0\n", b"T1\n", 1)
    (snapshot.artifact_dir / "exports/0002.gcode").write_bytes(raw)
    receipts[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    persist(snapshot, trace, receipts)
    result = verify_layer(snapshot)
    assert result.checks["path"].status == "pass"
    assert result.checks["business"].status == "fail"
    assert result.checks["business"].detail == "gcode_object_tool_changed"


def test_edit_control_and_requested_text_are_not_model_success_claims(evidence):
    snapshot, trace, receipts = evidence
    receipts[3]["details"]["control_class"] = "panel"
    persist(snapshot, trace, receipts)
    assert not verify_layer(snapshot).evidence_complete


def test_no_gui_edit_cannot_be_replaced_by_an_observe(evidence):
    snapshot, trace, receipts = evidence
    trace[3]["request"].update(method="observe", arguments={})
    trace[3]["response"]["tool"] = "observe"
    persist(snapshot, trace, receipts)
    assert not verify_layer(snapshot).evidence_complete


def test_click_outside_protocol_tab_band_cannot_complete_path(evidence):
    snapshot, trace, receipts = evidence
    trace[1]["request"].update(method="click", arguments={"x": 10, "y": 10})
    trace[1]["response"]["tool"] = "click"
    persist(snapshot, trace, receipts)
    result = verify_layer(snapshot)
    assert not result.evidence_complete
    assert result.checks["path"].detail == "click_outside_tab_band"


def test_worker_cancellation_waits_for_real_quiescence(evidence, monkeypatch):
    snapshot, *_ = evidence
    import harness.agent_layer_verify as module
    original, release = module.verify_layer, threading.Event()
    def blocked(s, **kwargs):
        release.wait(5)
        return original(s, **kwargs)
    monkeypatch.setattr(module, "verify_layer", blocked)
    handle = AgentLayerVerifier().start(snapshot)
    try:
        assert handle.worker.daemon and isinstance(handle.poll(), Pending)
        handle.cancel("timeout")
        assert isinstance(handle.start_cleanup().poll(), Pending)
    finally:
        release.set()
        handle.worker.join(5)
    assert isinstance(handle.start_cleanup().poll(), Done)
    assert not handle.poll().value.evidence_complete
