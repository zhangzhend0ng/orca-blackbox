"""Fixed m0 script shadow adapter; registration and backend are trusted code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

from . import host_guard
from .run_verdict import contract_digest
from .runtime_ports import CleanupOutcome, Done, ExecutionContext, ExecutionOutcome, Pending
from .win32_job import OwnedJobProcess

REPO = Path(__file__).resolve().parent.parent


class ScriptExecutor:
    synthetic = False
    kind = "script"

    def __init__(self, contract_sha256: str):
        if (type(contract_sha256) is not str or len(contract_sha256) != 64
                or any(x not in "0123456789abcdef" for x in contract_sha256)):
            raise ValueError("script executor requires exact registered contract digest")
        self.contract_sha256 = contract_sha256

    def start(self, context: ExecutionContext):
        if not host_guard.in_guest():
            raise PermissionError("script shadow execution requires a Hyper-V guest")
        if (context.contract.case_id != "m0_boot_check" or context.contract.executor != "script"
                or contract_digest(context.contract) != self.contract_sha256):
            raise ValueError("script executor is registered only for this exact m0 contract")
        artifact_dir = context.artifact_dir.resolve(strict=True)
        for relative in ("profile", "m0", "process.json", "script.log"):
            if (artifact_dir / relative).exists():
                raise FileExistsError("script output must start empty")
        argv = [sys.executable, str(REPO / "tests" / "engine" / "m0_boot_check.py"),
                "--datadir", str(artifact_dir / "profile"),
                "--output-dir", str(artifact_dir / "m0")]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"  # Match the independent verifier's log contract.
        for key in ("ORCA_BB_ALLOW_HOST", "ORCA_BB_CONF_EXTRA", "ORCA_GUI_TEST_MODE"):
            env.pop(key, None)
        started = time.time_ns()
        process = OwnedJobProcess.start(argv, cwd=REPO, log_path=artifact_dir / "script.log", env=env)
        return _ScriptHandle(process, context, started)


class _ScriptHandle:
    def __init__(self, process, context: ExecutionContext, started_at_ns: int):
        self.process, self.context = process, context
        self.started_at_ns = started_at_ns
        self.forced = False
        self.cancel_reason = None
        self.receipt_written = False
        self.closed = False

    def _observe(self):
        code, active = self.process.poll()
        if code is None or active != 0:
            return None
        if not self.receipt_written:
            receipt = {"schema_version": 1, "run_id": self.context.run_id,
                       "case_id": self.context.contract.case_id, "backend": "win32_job",
                       "pid": self.process.pid, "started_at_ns": self.started_at_ns,
                       "finished_at_ns": time.time_ns(), "exit_code": code,
                       "active_processes": 0, "job_assigned": True,
                       "forced_termination": self.forced, "cancel_reason": self.cancel_reason}
            with (self.context.artifact_dir / "process.json").open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.receipt_written = True
        return code

    def poll(self):
        code = self._observe()
        if code is None:
            return Pending()
        return Done(ExecutionOutcome("completed" if code == 0 and not self.forced else "failed"))

    def cancel(self, reason: str):
        if not self.closed:
            code, active = self.process.poll()
            if code is None or active:
                self.forced = True
                if self.cancel_reason is None:
                    self.cancel_reason = reason if reason in {
                        "cleanup", "execution_timeout", "cancelled", "adapter_error",
                        "desktop_quarantined"} else "external_cancel"
                self.process.terminate()

    def start_cleanup(self):
        self.cancel("cleanup")
        return _ScriptCleanup(self)


class _ScriptCleanup:
    def __init__(self, execution: _ScriptHandle):
        self.execution = execution

    def poll(self):
        operation = self.execution
        if operation.closed:
            return Done(CleanupOutcome(True))
        if operation._observe() is None:
            return Pending()
        operation.process.close()
        operation.closed = True
        return Done(CleanupOutcome(True))
