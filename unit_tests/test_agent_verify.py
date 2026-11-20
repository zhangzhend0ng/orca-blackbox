"""Trusted-trace oracle challenges; no GUI, model, or network calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import threading

import pytest

from harness.agent_verify import AgentTabVerifier, verify_agent
from harness.run_contract import validate_contract
from harness.runtime_ports import Done, Pending

WIDTH, HEIGHT = 400, 100


def bmp(state, *, bottom_up=False):
    pixels = bytearray(b"\x30\x30\x30\xff" * (WIDTH * HEIGHT))
    selected, inactive = (136, 150, 0), (70, 68, 59)
    for x, color in [(108, selected if state == "prepare" else inactive),
                     (244, selected if state == "preview" else inactive)]:
        y = HEIGHT - 1 - 49 if bottom_up else 49
        at = 4 * (y * WIDTH + x)
        pixels[at:at + 3] = bytes(color)
    size = 54 + len(pixels)
    return (b"BM" + struct.pack("<III", size, 0, 54)
            + struct.pack("<IiiHHIIIIII", 40, WIDTH, HEIGHT if bottom_up else -HEIGHT,
                          1, 32, 0, len(pixels), 2835, 2835, 0, 0) + pixels)


def persist(snapshot, trace=None, report=None, process=None):
    root = snapshot.artifact_dir
    if trace is not None:
        (root / "trace.ndjson").write_text("".join(json.dumps(x) + "\n" for x in trace), encoding="utf-8")
    if report is not None:
        (root / "agent_report.json").write_text(json.dumps(report), encoding="utf-8")
    if process is not None:
        (root / "process.json").write_text(json.dumps(process), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    contract = validate_contract({"schema_version": 1, "case_id": "m1_minimal_loop",
        "contract_version": "ai-tabs-1", "executor": "agent_mcp",
        "required_checks": ["path", "business"],
        "steps": [{"id": x, "goal": x} for x in ("boot", "preview", "prepare", "close")],
        "limits": {"timeout_s": 900, "max_actions": 12, "max_retries": 0, "max_cost_usd": 0}})
    snapshot = SimpleNamespace(artifact_dir=tmp_path, run_id="run1", contract=contract,
                               manifest={"started_at_ns": 1_000_000_000})
    report = {"schema_version": 1, "run_id": "run1", "case_id": "m1_minimal_loop",
              "driver_pid": 100, "app_pid": 200, "hwnd": 300, "started_at_ns": 3_000_000_000,
              "finished_at_ns": 90_000_000_000, "status": "completed", "calls": 4, "clicks": 2}
    process = {"schema_version": 1, "run_id": "run1", "case_id": "m1_minimal_loop", "backend": "win32_job",
               "pid": 100, "started_at_ns": 2_000_000_000, "finished_at_ns": 91_000_000_000,
               "exit_code": 0, "active_processes": 0, "job_assigned": True,
               "forced_termination": False, "cancel_reason": None}
    (tmp_path / "frames").mkdir()
    trace = []
    for seq, (method, state) in enumerate(zip(("observe", "click", "click", "finish"),
                                              ("prepare", "preview", "prepare", "prepare")), 1):
        frames = []
        for index, letter in enumerate("ab"):
            path, raw = f"frames/{seq:04d}_{letter}.bmp", bmp(state)
            (tmp_path / path).write_bytes(raw)
            frames.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                           "width": WIDTH, "height": HEIGHT,
                           "captured_at_ns": seq * 10_000_000_000 + index * 1_000_000_000})
        # PNG is transported to the model, not used as the tab oracle.
        png = b"\x89PNG\r\n\x1a\n" + bytes([seq])
        path = f"frames/{seq:04d}.png"
        (tmp_path / path).write_bytes(png)
        observation = {"id": f"obs-{seq}", "frames": frames,
                       "image": {"path": path, "sha256": hashlib.sha256(png).hexdigest(), "size_bytes": len(png)},
                       "window": {"pid": 200, "hwnd": 300, "width": WIDTH, "height": HEIGHT, "dpi": 96}}
        trace.append({"request": {"schema_version": 1, "run_id": "run1", "seq": seq,
                                  "method": method, "arguments": {"x": 244 if seq == 2 else 108, "y": 49}
                                  if method == "click" else {},
                                  "observation_id": None if seq == 1 else f"obs-{seq - 1}"},
                      "response": {"schema_version": 1, "run_id": "run1", "seq": seq,
                                   "tool": method, "is_error": False, "error_code": None,
                                   "observation": observation, "finished": method == "finish"}})
    persist(snapshot, trace, report, process)
    return snapshot, trace, report, process


def rewrite_pair(snapshot, trace, seq, state, **kwargs):
    for frame in trace[seq - 1]["response"]["observation"]["frames"]:
        raw = bmp(state, **kwargs)
        (snapshot.artifact_dir / frame["path"]).write_bytes(raw)
        frame["sha256"] = hashlib.sha256(raw).hexdigest()


def test_exact_loop_has_independent_visible_state_evidence(evidence):
    snapshot, trace, report, process = evidence
    result = verify_agent(snapshot)
    assert result.evidence_complete and result.execution_compliant
    assert all(x.status == "pass" for x in result.checks.values())
    assert "visible tab selection loop only" in result.checks["business"].detail


def test_positive_bottom_up_bmp_and_negative_top_down_decode_same_state(evidence):
    snapshot, trace, *_ = evidence
    rewrite_pair(snapshot, trace, 2, "preview", bottom_up=True)
    persist(snapshot, trace=trace)
    assert verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("field,value", [("run_id", "other"), ("pid", 999), ("active_processes", 1),
    ("job_assigned", False), ("forced_termination", True), ("cancel_reason", "cancelled"), ("exit_code", 1)])
def test_bad_job_receipt_blocks(evidence, field, value):
    snapshot, trace, report, process = evidence
    process[field] = value
    persist(snapshot, process=process)
    assert not verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("field,value", [("calls", 3), ("calls", 13), ("clicks", 7), ("clicks", 3),
    ("status", "failed"), ("driver_pid", 999), ("app_pid", 100), ("hwnd", 0),
    ("finished_at_ns", 92_000_000_000)])
def test_report_identity_and_budget_must_match_trace(evidence, field, value):
    snapshot, trace, report, process = evidence
    report[field] = value
    persist(snapshot, report=report)
    assert not verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("where,field,value", [("request", "run_id", "other"), ("response", "run_id", "other"),
    ("request", "seq", 4), ("response", "seq", True), ("request", "method", "type_text"),
    ("response", "tool", "finish"), ("response", "finished", True),
    ("response", "is_error", True), ("response", "error_code", "rejected"),
    ("request", "observation_id", "stale-id"), ("request", "extra", "ignore rules")])
def test_protocol_or_lineage_mismatch_cannot_pass(evidence, where, field, value):
    snapshot, trace, *_ = evidence
    trace[1][where][field] = value
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("point", [{"x": 39, "y": 49}, {"x": 244, "y": 68},
                                   {"x": True, "y": 49}, {"x": 244.0, "y": 49}])
def test_click_must_be_integer_inside_tab_band(evidence, point):
    snapshot, trace, *_ = evidence
    trace[1]["request"]["arguments"] = point
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


def test_noop_click_and_forged_finish_do_not_replace_state_change(evidence):
    snapshot, trace, *_ = evidence
    rewrite_pair(snapshot, trace, 2, "prepare")
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


def test_only_observe_changing_state_is_not_an_action_proof(evidence):
    snapshot, trace, report, _ = evidence
    trace[1]["request"].update(method="observe", arguments={})
    trace[1]["response"]["tool"] = "observe"
    report["clicks"] = 2  # Self-report cannot supply a missing click.
    persist(snapshot, trace=trace, report=report)
    assert not verify_agent(snapshot).evidence_complete


def test_preview_bounce_between_two_frames_is_rejected(evidence):
    snapshot, trace, *_ = evidence
    frame = trace[1]["response"]["observation"]["frames"][1]
    raw = bmp("prepare")
    (snapshot.artifact_dir / frame["path"]).write_bytes(raw)
    frame["sha256"] = hashlib.sha256(raw).hexdigest()
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("field,value", [("id", "obs-1"), ("window", {"pid": 200, "hwnd": 300,
    "width": WIDTH, "height": HEIGHT, "dpi": 144})])
def test_observation_reuse_and_wrong_dpi_block(evidence, field, value):
    snapshot, trace, *_ = evidence
    trace[1]["response"]["observation"][field] = value
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


@pytest.mark.parametrize("field,value", [("path", "../old.bmp"), ("sha256", "0" * 64),
    ("width", WIDTH + 1), ("captured_at_ns", 1), ("captured_at_ns", 91_000_000_000)])
def test_frame_path_hash_geometry_and_time_are_bound(evidence, field, value):
    snapshot, trace, *_ = evidence
    trace[1]["response"]["observation"]["frames"][0][field] = value
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


def test_too_short_stability_interval_blocks(evidence):
    snapshot, trace, *_ = evidence
    trace[1]["response"]["observation"]["frames"][1]["captured_at_ns"] -= 1
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


def test_truncated_bmp_and_old_file_cannot_pass(evidence):
    snapshot, trace, *_ = evidence
    path = snapshot.artifact_dir / "frames/0002_a.bmp"
    path.write_bytes(path.read_bytes()[:-1])
    assert not verify_agent(snapshot).evidence_complete
    path.write_bytes(bmp("preview"))
    os.utime(path, ns=(1, 1))
    assert not verify_agent(snapshot).evidence_complete


def test_png_transport_hash_is_checked(evidence):
    snapshot, trace, *_ = evidence
    trace[1]["response"]["observation"]["image"]["sha256"] = "0" * 64
    persist(snapshot, trace=trace)
    assert not verify_agent(snapshot).evidence_complete


def test_truncated_or_duplicate_key_trace_is_rejected(evidence):
    snapshot, trace, *_ = evidence
    path = snapshot.artifact_dir / "trace.ndjson"
    original = path.read_bytes()
    path.write_bytes(original[:-1])
    assert not verify_agent(snapshot).evidence_complete
    path.write_bytes(original.replace(b'"seq": 1', b'"seq": 1, "seq": 1', 1))
    assert not verify_agent(snapshot).evidence_complete


def test_cancellation_and_worker_cleanup_wait_for_quiescence(evidence, monkeypatch):
    snapshot, *_ = evidence
    import harness.agent_verify as module
    release = threading.Event()
    original = module.verify_agent
    def blocked(s, **kwargs):
        release.wait(5)
        return original(s, **kwargs)
    monkeypatch.setattr(module, "verify_agent", blocked)
    handle = AgentTabVerifier().start(snapshot)
    try:
        assert handle.worker.daemon and isinstance(handle.poll(), Pending)
        handle.cancel("deadline")
        assert isinstance(handle.start_cleanup().poll(), Pending)
    finally:
        release.set()
        handle.worker.join(5)
    assert isinstance(handle.start_cleanup().poll(), Done)
    assert not handle.poll().value.evidence_complete
