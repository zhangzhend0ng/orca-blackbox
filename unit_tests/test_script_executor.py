"""Fake owned-process API only: no app launch, GUI, shell, or real child process."""
import json
from pathlib import Path

import pytest

from harness import script_executor as module
from harness.run_contract import validate_contract
from harness.run_verdict import contract_digest
from harness.runtime import run_once
from harness.runtime_ports import Done, ExecutionContext, Pending


@pytest.fixture
def contract():
    return validate_contract({"schema_version": 1, "case_id": "m0_boot_check",
        "contract_version": "1", "executor": "script", "required_checks": ["path", "business"],
        "steps": [{"id": "boot", "goal": "Launch and capture"}],
        "limits": {"timeout_s": 10, "max_actions": 10, "max_retries": 0, "max_cost_usd": 0}})


class FakeOwnedProcess:
    pid = 123

    def __init__(self):
        self.code, self.active, self.terminated, self.closed = None, 2, False, False

    def poll(self):
        return self.code, self.active

    def terminate(self):
        self.terminated = True  # Termination request does not prove quiescence.

    def close(self):
        assert self.active == 0
        self.closed = True


@pytest.fixture
def setup_adapter(tmp_path, contract, monkeypatch):
    process = FakeOwnedProcess()
    captured = {}
    def start(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return process
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: True)
    monkeypatch.setattr(module.OwnedJobProcess, "start", start)
    context = ExecutionContext(contract, "test-run", tmp_path)
    return module.ScriptExecutor(contract_digest(contract)), context, process, captured


def test_fixed_m0_arguments_and_environment_are_not_user_commands(setup_adapter, monkeypatch):
    adapter, context, process, captured = setup_adapter
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    monkeypatch.setenv("ORCA_BB_CONF_EXTRA", "untrusted")
    monkeypatch.setenv("PYTHONIOENCODING", "cp936")
    handle = adapter.start(context)
    assert isinstance(handle.poll(), Pending)
    assert captured["argv"][1] == str(module.REPO / "tests/engine/m0_boot_check.py")
    assert "--fresh" not in captured["argv"]
    assert captured["argv"][2:] == ["--datadir", str(context.artifact_dir / "profile"),
                                     "--output-dir", str(context.artifact_dir / "m0")]
    assert "ORCA_BB_ALLOW_HOST" not in captured["env"]
    assert "ORCA_BB_CONF_EXTRA" not in captured["env"]
    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["cwd"] == module.REPO


def test_driver_exit_does_not_confirm_live_descendants(setup_adapter):
    adapter, context, process, _ = setup_adapter
    handle = adapter.start(context)
    process.code = 0
    assert isinstance(handle.poll(), Pending)
    assert not (context.artifact_dir / "process.json").exists()
    process.active = 0
    assert handle.poll().value.status == "completed"
    receipt = json.loads((context.artifact_dir / "process.json").read_text())
    assert receipt["backend"] == "win32_job" and receipt["active_processes"] == 0
    assert receipt["job_assigned"] is True and receipt["forced_termination"] is False
    assert receipt["finished_at_ns"] >= receipt["started_at_ns"]
    before = (context.artifact_dir / "process.json").read_bytes()
    assert isinstance(handle.poll(), Done)
    assert (context.artifact_dir / "process.json").read_bytes() == before


def test_cancel_and_cleanup_wait_for_job_empty(setup_adapter):
    adapter, context, process, _ = setup_adapter
    handle = adapter.start(context)
    handle.cancel("execution_timeout")
    assert process.terminated
    cleanup = handle.start_cleanup()
    assert isinstance(cleanup.poll(), Pending)
    assert not process.closed
    process.code, process.active = 1, 0
    assert cleanup.poll().value.confirmed
    assert process.closed
    receipt = json.loads((context.artifact_dir / "process.json").read_text())
    assert receipt["forced_termination"] is True
    assert receipt["cancel_reason"] == "execution_timeout"


def test_allow_host_never_bypasses_guest_guard(setup_adapter, monkeypatch):
    adapter, context, _, captured = setup_adapter
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: False)
    with pytest.raises(PermissionError, match="Hyper-V"):
        adapter.start(context)
    assert captured == {}


def test_script_digest_mismatch_and_existing_artifact_are_rejected(setup_adapter):
    adapter, context, _, captured = setup_adapter
    other = module.ScriptExecutor("0" * 64)
    with pytest.raises(ValueError, match="exact m0"):
        other.start(context)
    (context.artifact_dir / "profile").mkdir()
    with pytest.raises(FileExistsError):
        adapter.start(context)
    assert captured == {}


def test_real_runtime_guard_runs_before_root_or_adapter(tmp_path, contract, monkeypatch):
    monkeypatch.setattr(module.host_guard, "in_guest", lambda: False)
    monkeypatch.setenv("ORCA_BB_ALLOW_HOST", "1")
    with pytest.raises(PermissionError, match="Hyper-V"):
        run_once(contract, module.ScriptExecutor(contract_digest(contract)), {},
                 root=tmp_path, execution_mode="guest_script")
    assert list(tmp_path.iterdir()) == []


def test_win32_backend_assigns_suspended_child_before_resume(tmp_path, monkeypatch):
    import os
    if os.name != "nt":
        pytest.skip("Win32 API binding test; no process is launched")
    import _winapi
    from harness import win32_job as job
    calls = []
    class Func:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    class Kernel:
        CreateJobObjectW = Func(lambda *_: 99)
        SetInformationJobObject = Func(lambda *_: calls.append("limits") or 1)
        AssignProcessToJobObject = Func(lambda *_: calls.append("assign") or 1)
        ResumeThread = Func(lambda *_: calls.append("resume") or 1)
        TerminateJobObject = Func(lambda *_: calls.append("terminate") or 1)
        QueryInformationJobObject = Func(lambda *_: 1)
    def create(executable, argv, _a, _b, inherited, flags, env, cwd, si):
        calls.append("suspended_create")
        assert executable.endswith("python.exe") and flags & 0x4
        assert inherited and 99 not in si.lpAttributeList["handle_list"]
        return 100, 101, 123, 124
    monkeypatch.setattr(job.C, "WinDLL", lambda *_a, **_k: Kernel())
    monkeypatch.setattr(_winapi, "CreateProcess", create)
    monkeypatch.setattr(_winapi, "CloseHandle", lambda *_: None)
    process = job.OwnedJobProcess.start(["C:/python.exe", "fixed.py"], cwd=tmp_path,
                                       log_path=tmp_path / "script.log", env={})
    assert calls == ["limits", "suspended_create", "assign", "resume"]
    process._log.close()


@pytest.mark.parametrize("failure", ["assign", "resume"])
def test_win32_start_failure_stops_and_closes_only_owned_handles(tmp_path, monkeypatch, failure):
    import os
    if os.name != "nt":
        pytest.skip("Win32 API binding test; no process is launched")
    import _winapi
    from harness import win32_job as job
    terminated, closed = [], []
    class Func:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    class Kernel:
        CreateJobObjectW = Func(lambda *_: 99)
        SetInformationJobObject = Func(lambda *_: 1)
        AssignProcessToJobObject = Func(lambda *_: 0 if failure == "assign" else 1)
        ResumeThread = Func(lambda *_: 0xFFFFFFFF)
        TerminateJobObject = Func(lambda *_: 1)
        QueryInformationJobObject = Func(lambda *_: 1)
    monkeypatch.setattr(job.C, "WinDLL", lambda *_a, **_k: Kernel())
    monkeypatch.setattr(_winapi, "CreateProcess", lambda *_: (100, 101, 123, 124))
    monkeypatch.setattr(_winapi, "TerminateProcess", lambda pid, _code: terminated.append(pid))
    monkeypatch.setattr(_winapi, "CloseHandle", lambda handle: closed.append(handle))
    with pytest.raises(OSError):
        job.OwnedJobProcess.start(["C:/python.exe", "fixed.py"], cwd=tmp_path,
                                  log_path=tmp_path / "script.log", env={})
    assert terminated == [100]
    assert set(closed) == {99, 100, 101}
    with (tmp_path / "script.log").open("ab") as stream:
        stream.write(b"closed")


def test_failed_termination_cannot_return_cleanup_confirmation(setup_adapter):
    adapter, context, process, _ = setup_adapter
    handle = adapter.start(context)
    def fail():
        raise OSError("terminate failed")
    process.terminate = fail
    with pytest.raises(OSError, match="terminate failed"):
        handle.start_cleanup()
    assert not process.closed
    assert not (context.artifact_dir / "process.json").exists()
