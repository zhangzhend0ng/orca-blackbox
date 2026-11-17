"""Pure authority/evidence challenges. These are NOT GUI coverage."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.native_save_policy import validate_input
from harness.native_save_session import native_contract, verify_saved, NATIVE_SUT_SHA256
from harness.agent_protocol import LAYER_FIXTURE
from harness.run_verdict import contract_digest
from unit_tests.test_agent_project_verify import project_bytes
from unit_tests.test_agent_layer_verify import gcode

OUTPUT = r"C:\owned\0001.3mf"


@pytest.mark.parametrize("tool,args", [
    ("Shortcut", {"shortcut": "win+r"}),
    ("Shortcut", {"shortcut": "alt+tab"}),
    ("Type", {"loc": [300, 400], "text": "powershell.exe"}),
    ("Type", {"loc": [300, 400], "text": r"C:\other\0001.3mf"}),
    ("Type", {"loc": [300, 400], "text": "0.24\ncalc"}),
    ("Type", {"loc": [300, 400], "text": "0.24", "clear": "true"}),
    ("Click", {"loc": [True, 30]}),
    ("Click", {"loc": [1920, 30]}),
    ("Click", {"label": 1}),
    ("Screenshot", {"save_path": r"C:\file.png"}),
    ("Snapshot", {"use_dom": True}),
    ("Wait", {"duration": float("inf")}),
    ("Wait", {"duration": 90}),
    ("PowerShell", {"command": "anything"}),
])
def test_native_authority_rejects_escape_and_unbounded_inputs(tool, args):
    with pytest.raises(ValueError):
        validate_input(tool, args, OUTPUT)


@pytest.mark.parametrize("tool,args", [
    ("Type", {"loc": [300, 400], "text": "0.24", "clear": True, "press_enter": True}),
    ("Type", {"loc": [300, 400], "text": OUTPUT}),
    ("Shortcut", {"shortcut": "Ctrl+Shift+S"}),
    ("Click", {"loc": [300, 400], "clicks": 2}),
    ("Snapshot", {"use_vision": True, "use_annotation": False}),
])
def test_native_authority_accepts_resource_scoped_inputs(tool, args):
    validate_input(tool, args, OUTPUT)


def save_json(root, name, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def native_evidence(tmp_path):
    root = tmp_path
    for d in ("input", "projects", "proof", "exports"):
        (root / d).mkdir()
    fixture = (Path(__file__).resolve().parents[1] / LAYER_FIXTURE).read_bytes()
    saved = project_bytes(fixture)
    (root / "input/fixture.3mf").write_bytes(fixture)
    for name in ("projects/0001.3mf", "proof/0001.3mf"):
        (root / name).write_bytes(saved)
    final = gcode("0.24")
    (root / "exports/0001.gcode").write_bytes(final)
    run = "a"*32
    proof = {"run_id": run, "contract_sha256": contract_digest(native_contract()),
        "sut_sha256": NATIVE_SUT_SHA256,
        "input_stopped_at_ns": 100, "old_closed_at_ns": 200, "frozen_at_ns": 300,
        "reopen_started_at_ns": 400, "exported_at_ns": 500,
        "mcp_active_processes": 0, "old_exit_code": 0, "old_pid": 123,
        "reopened_closed": True, "reopened_exit_code": 0, "output_path": OUTPUT,
        "project_sha256": hashlib.sha256(saved).hexdigest(), "gcode_sha256": hashlib.sha256(final).hexdigest()}
    save_json(root, "proof.json", proof)
    save_json(root, "process.json", {"run_id": run, "exit_code": 0, "active_processes": 0,
        "job_assigned": True, "forced_termination": False})
    save_json(root, "host_done.json", {"run_id": run, "native_ok": True, "host_active_processes": 0,
        "host_forced": False, "tool_count": 2})
    trace = [{"tool": "Type", "arguments": {"text": text}, "error": None,
              "finished_at_ns": 90, "window": {"app_pid": 123}} for text in ("0.24", OUTPUT)]
    (root / "native_trace.ndjson").write_text("\n".join(json.dumps(t) for t in trace))
    return SimpleNamespace(contract=native_contract(), artifact_dir=root, run_id=run, manifest={"started_at_ns": 1})


def test_native_business_proof_accepts_frozen_fresh_profile_chain(native_evidence):
    result = verify_saved(native_evidence)
    assert result.evidence_complete and result.execution_compliant
    assert result.checks["business"].status == "pass"


@pytest.mark.parametrize("fault", ["old_project", "changed_frozen_file", "late_input", "missing_reopen", "host_error", "forced_cleanup", "malformed_zip", "failed_reopen", "wrong_sut"])
def test_native_business_proof_rejects_wrong_content_and_custody(native_evidence, fault):
    root = native_evidence.artifact_dir
    if fault == "old_project":
        old = (root / "input/fixture.3mf").read_bytes()
        for name in ("projects/0001.3mf", "proof/0001.3mf"):
            (root / name).write_bytes(old)
        p = json.loads((root / "proof.json").read_text());p["project_sha256"] = hashlib.sha256(old).hexdigest();save_json(root,"proof.json",p)
    elif fault == "malformed_zip":
        raw = b"PK\x03\x04broken archive"
        for name in ("projects/0001.3mf", "proof/0001.3mf"):
            (root / name).write_bytes(raw)
        p=json.loads((root / "proof.json").read_text());p["project_sha256"]=hashlib.sha256(raw).hexdigest();save_json(root,"proof.json",p)
    elif fault in {"failed_reopen", "wrong_sut"}:
        p=json.loads((root / "proof.json").read_text());p["reopened_exit_code" if fault == "failed_reopen" else "sut_sha256"]=1;save_json(root,"proof.json",p)
    elif fault == "changed_frozen_file":
        (root / "proof/0001.3mf").write_bytes(b"different")
    elif fault in {"late_input", "missing_reopen"}:
        p = json.loads((root / "proof.json").read_text())
        p["input_stopped_at_ns" if fault == "late_input" else "reopen_started_at_ns"] = 2
        save_json(root,"proof.json",p)
    elif fault == "host_error":
        p = json.loads((root / "host_done.json").read_text());p["native_ok"] = False;save_json(root,"host_done.json",p)
    else:
        p = json.loads((root / "process.json").read_text());p["forced_termination"] = True;save_json(root,"process.json",p)
    assert not verify_saved(native_evidence).evidence_complete


def test_native_runtime_refuses_host_even_with_debug_opt_out(tmp_path, monkeypatch):
    from harness import host_guard
    from harness.runtime import run_once
    from harness.native_save_session import NativeSaveExecutor, NativeSaveVerifier
    monkeypatch.setattr(host_guard, "in_guest", lambda: False)
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    contract = native_contract(); digest=contract_digest(contract)
    with pytest.raises(PermissionError, match="Hyper-V guest"):
        run_once(contract, NativeSaveExecutor(digest), {digest: NativeSaveVerifier()},
                 root=tmp_path, run_id="b"*32, execution_mode="guest_native")


def test_native_runtime_rejects_unregistered_verifier_before_gui(tmp_path, monkeypatch):
    from harness import host_guard
    from harness.runtime import run_once
    from harness.native_save_session import NativeSaveExecutor
    monkeypatch.setattr(host_guard, "in_guest", lambda: True)
    contract=native_contract();digest=contract_digest(contract)
    with pytest.raises(ValueError, match="unregistered native verifier"):
        run_once(contract, NativeSaveExecutor(digest), {digest: SimpleNamespace(synthetic=False)},
                 root=tmp_path, run_id="b"*32, execution_mode="guest_native")


def test_native_cleanup_waits_for_natural_helpers_then_completes(tmp_path, monkeypatch):
    from harness.native_save_session import NativeSaveHandle
    from harness.runtime_ports import Pending, Done
    ticks = [0.0]
    monkeypatch.setattr("harness.native_save_session.time.monotonic", lambda: ticks[0])
    class Job:
        pid, active, terminated = 123, 1, False
        def poll(self):return 0,self.active
        def terminate(self):self.terminated=True;self.active=0
    job=Job();ctx=SimpleNamespace(run_id="c"*32,contract=native_contract(),artifact_dir=tmp_path)
    h=NativeSaveHandle(job,ctx,1)
    assert isinstance(h.poll(),Pending) and not job.terminated
    ticks[0]=2;job.active=0
    assert isinstance(h.poll(),Done) and not h.forced


def test_native_cleanup_stops_only_owned_helpers_after_grace(tmp_path, monkeypatch):
    from harness.native_save_session import NativeSaveHandle
    ticks=[0.0]
    monkeypatch.setattr("harness.native_save_session.time.monotonic",lambda:ticks[0])
    class Job:
        pid,active,terminated=123,1,False
        def poll(self):return 0,self.active
        def terminate(self):self.terminated=True;self.active=0
    job=Job();ctx=SimpleNamespace(run_id="c"*32,contract=native_contract(),artifact_dir=tmp_path)
    h=NativeSaveHandle(job,ctx,1);h.poll();ticks[0]=11;h.poll()
    assert job.terminated and h.forced
