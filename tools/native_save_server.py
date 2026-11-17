"""Original pinned Windows-MCP plus a deterministic authority middleware."""
from pathlib import Path
import argparse
import asyncio
import json
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from harness import host_guard
    from harness.agent_protocol import valid_run_id
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    valid_run_id(args.run_id)
    if not host_guard.in_guest():
        raise PermissionError("native server requires guest")
    root = REPO / "artifacts/v3" / args.run_id / "artifacts"
    from harness.native_save_policy import InputGuard, NATIVE_TOOLS
    scope = json.loads((root / "scope.json").read_text())
    guard = InputGuard(scope, root)
    from fastmcp.server.middleware import Middleware
    from fastmcp.exceptions import ToolError
    from windows_mcp import __main__ as original

    class Authority(Middleware):
        def __init__(self):
            self.calls, self.lock = 0, asyncio.Lock()

        async def on_call_tool(self, context, call_next):
            async with self.lock:
                self.calls += 1
                name, arguments = context.message.name, context.message.arguments or {}
                row = {"seq": self.calls, "tool": name if name in NATIVE_TOOLS else "rejected_tool", "arguments": {},
                       "run_id": args.run_id, "level": "INFO", "message": "native_tool_call",
                       "started_at_ns": time.time_ns(), "error": None}
                try:
                    if self.calls > 40:
                        raise ValueError("native_tool_budget")
                    row["window"] = guard.check(name, arguments)
                    row["arguments"] = arguments  # Only validated numeric/path/key data is logged.
                    return await call_next(context)
                except Exception as exc:
                    code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("native_") else "native_tool_failed"
                    row["error"] = type(exc).__name__+":"+code[:120]
                    row["level"] = "ERROR"
                    raise ToolError(row["error"]) from exc
                finally:
                    row["finished_at_ns"] = time.time_ns()
                    with (root / "native_trace.ndjson").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(row, ensure_ascii=True)+"\n")

    original._build_mcp().add_middleware(Authority())
    original.main(["serve", "--transport", "streamable-http", "--host", "127.0.0.1",
                   "--port", "18789", "--stateless-http", "--no-control", "--tools",
                   ",".join(sorted(NATIVE_TOOLS)), "--config", str(root / "config.toml")])


if __name__ == "__main__":
    main()
