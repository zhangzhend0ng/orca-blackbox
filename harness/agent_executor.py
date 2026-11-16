"""Fixed guest tool worker, with the existing owned Job lifecycle; no model keys."""
from __future__ import annotations

import os
import sys
import time

from . import host_guard
from .run_verdict import contract_digest
from .script_executor import REPO, _ScriptHandle
from .win32_job import OwnedJobProcess


class AgentExecutor:
    synthetic = False
    kind = "agent_mcp"

    def __init__(self, contract_sha256: str):
        if (type(contract_sha256) is not str or len(contract_sha256) != 64
                or any(x not in "0123456789abcdef" for x in contract_sha256)):
            raise ValueError("agent executor requires exact registered digest")
        self.contract_sha256 = contract_sha256

    def start(self, context):
        if not host_guard.in_guest():
            raise PermissionError("agent executor requires Hyper-V guest")
        if (context.contract.case_id != "m1_minimal_loop"
                or context.contract.contract_version != "ai-tabs-1"
                or context.contract.executor != "agent_mcp"
                or contract_digest(context.contract) != self.contract_sha256):
            raise ValueError("agent executor supports only this exact tab contract")
        artifacts = context.artifact_dir.resolve(strict=True)
        if any(artifacts.iterdir()):
            raise FileExistsError("agent artifacts must start empty")
        env = {key: value for key, value in os.environ.items()
               if not key.upper().endswith(("_API_KEY", "_TOKEN", "_SECRET"))}
        for key in ("ORCA_BB_ALLOW_HOST", "ORCA_BB_CONF_EXTRA", "ORCA_GUI_TEST_MODE"):
            env.pop(key, None)
        env["PYTHONIOENCODING"] = "utf-8"
        argv = [sys.executable, str(REPO / "harness" / "agent_guest.py"),
                "--artifact-dir", str(artifacts), "--run-id", context.run_id,
                "--contract-sha256", self.contract_sha256]
        started = time.time_ns()
        process = OwnedJobProcess.start(argv, cwd=REPO, log_path=artifacts / "agent.log", env=env)
        return _ScriptHandle(process, context, started)
