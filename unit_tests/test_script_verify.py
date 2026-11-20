"""Independent m0 evidence challenges, using generated BMPs without a GUI."""
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from harness.script_verify import M0ScriptVerifier, verify_m0
from harness.runtime_ports import Done


def bmp(width=3, height=2, uniform=False):
    pixels = bytes([0, 0, 0, 255] * (width * height)) if uniform else bytes(
        value for i in range(width * height) for value in (i, i * 2, i * 3, 255))
    size = 54 + len(pixels)
    return (b"BM" + struct.pack("<III", size, 0, 54)
            + struct.pack("<IiiHHIIIIII", 40, width, height, 1, 32, 0, len(pixels), 2835, 2835, 0, 0)
            + pixels)


@pytest.fixture
def snapshot(tmp_path):
    (tmp_path / "m0").mkdir()
    report = {"schema_version": 1, "case_id": "m0_boot_check", "driver_pid": 100,
              "app_pid": 200, "hwnd": 300,
              "phases": ["launched", "preflight", "captures_complete", "close_requested", "closed"],
              "captures": [{"filename": f"startup_{i}.bmp", "width": 3, "height": 2} for i in range(3)],
              "grab": False, "keep": False}
    (tmp_path / "m0" / "report.json").write_text(json.dumps(report), encoding="utf-8")
    process = {"schema_version": 1, "run_id": "run1", "case_id": "m0_boot_check",
               "backend": "win32_job", "pid": 100, "started_at_ns": 2_000_000_000,
               "finished_at_ns": 3_000_000_000, "exit_code": 0,
               "active_processes": 0, "job_assigned": True, "forced_termination": False, "cancel_reason": None}
    (tmp_path / "process.json").write_text(json.dumps(process), encoding="utf-8")
    log = ["[m0-evidence] launched driver_pid=100 app_pid=200 hwnd=300"]
    for i in range(3):
        (tmp_path / "m0" / f"startup_{i}.bmp").write_bytes(bmp())
        log.append(f"[m0] capture {i}: 3x2 -> startup_{i}.bmp")
    log.append("[m0] app closed")
    (tmp_path / "script.log").write_text("\n".join(log), encoding="utf-8")
    return SimpleNamespace(artifact_dir=tmp_path, run_id="run1",
                           manifest={"started_at_ns": 1_000_000_000},
                           contract=SimpleNamespace(case_id="m0_boot_check", executor="script",
                               steps=[SimpleNamespace(id=name) for name in ("boot", "capture", "close")]))


def mutate_json(snapshot, filename, field, value):
    path = snapshot.artifact_dir / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def test_valid_report_bmp_log_and_trusted_job_receipt_support_bootstrap_only(snapshot):
    result = verify_m0(snapshot)
    assert result.evidence_complete and result.execution_compliant
    assert all(x.status == "pass" for x in result.checks.values())
    assert "bootstrap" in result.checks["business"].detail
    handle = M0ScriptVerifier().start(snapshot)
    handle._worker.join(timeout=5)
    assert not handle._worker.is_alive()
    assert isinstance(handle.poll(), Done)


def test_verifier_cleanup_waits_for_real_worker_quiescence(snapshot, monkeypatch):
    import threading
    from harness import script_verify
    from harness.runtime_ports import Pending
    release = threading.Event()
    original = script_verify.verify_m0
    def blocked(s, **kwargs):
        release.wait(5)
        return original(s, **kwargs)
    monkeypatch.setattr(script_verify, "verify_m0", blocked)
    handle = M0ScriptVerifier().start(snapshot)
    try:
        assert handle._worker.daemon is True
        assert isinstance(handle.poll(), Pending)
        handle.cancel("deadline")
        assert isinstance(handle.start_cleanup().poll(), Pending)
    finally:
        release.set()
        handle._worker.join(timeout=5)
    assert isinstance(handle.start_cleanup().poll(), Done)
    assert not handle.poll().value.evidence_complete


@pytest.mark.parametrize("field,value", [("run_id", "other"), ("case_id", "m2"),
    ("backend", "process_poll"), ("pid", 999), ("active_processes", 1),
    ("job_assigned", False), ("forced_termination", True), ("exit_code", 1),
    ("active_processes", False), ("started_at_ns", 0), ("finished_at_ns", 1),
    ("cancel_reason", "execution_timeout")])
def test_bad_job_receipt_cannot_become_pass(snapshot, field, value):
    mutate_json(snapshot, "process.json", field, value)
    assert not verify_m0(snapshot).evidence_complete


@pytest.mark.parametrize("field,value", [("grab", True), ("keep", True), ("app_pid", 100),
    ("hwnd", 0), ("driver_pid", 200), ("phases", ["launched", "closed"]),
    ("captures", []), ("schema_version", True)])
def test_incomplete_or_mismatched_report_cannot_pass(snapshot, field, value):
    mutate_json(snapshot, "m0/report.json", field, value)
    assert not verify_m0(snapshot).evidence_complete


@pytest.mark.parametrize("bad", [b"not a BMP", bmp()[:-1], b"BM" + b"\x00" * 52, bmp(uniform=True)])
def test_invalid_truncated_or_uniform_capture_is_not_rendering_evidence(snapshot, bad):
    (snapshot.artifact_dir / "m0/startup_1.bmp").write_bytes(bad)
    assert not verify_m0(snapshot).evidence_complete


def test_header_dimensions_must_match_report(snapshot):
    (snapshot.artifact_dir / "m0/startup_0.bmp").write_bytes(bmp(2, 2))
    assert not verify_m0(snapshot).evidence_complete


def test_success_log_and_exit_zero_alone_are_insufficient(snapshot):
    for p in (snapshot.artifact_dir / "m0").glob("*.bmp"):
        p.unlink()
    (snapshot.artifact_dir / "script.log").write_text("[m0] GREEN\n[m0] app closed", encoding="utf-8")
    assert not verify_m0(snapshot).evidence_complete


def test_capture_log_order_is_checked(snapshot):
    p = snapshot.artifact_dir / "script.log"
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join([lines[0], lines[2], lines[1], *lines[3:]]), encoding="utf-8")
    assert not verify_m0(snapshot).evidence_complete


def test_stale_evidence_is_not_accepted(snapshot):
    p = snapshot.artifact_dir / "m0/startup_0.bmp"
    os.utime(p, ns=(1, 1))
    assert not verify_m0(snapshot).evidence_complete


def test_duplicate_report_keys_rejected(snapshot):
    p = snapshot.artifact_dir / "m0/report.json"
    text = p.read_text(encoding="utf-8")
    p.write_text(text[:-1] + ',"grab": false}', encoding="utf-8")
    assert not verify_m0(snapshot).evidence_complete


def test_verifier_accepts_only_bootstrap_intent(snapshot):
    snapshot.contract.steps = [SimpleNamespace(id="slice")]
    assert not verify_m0(snapshot).evidence_complete


def test_cancellation_during_chunk_reads_never_becomes_pass(snapshot):
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 6
    result = verify_m0(snapshot, cancelled=cancelled)
    assert not result.evidence_complete
    assert result.checks["path"].detail == "verification_cancelled"
