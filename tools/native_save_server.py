"""Original pinned Windows-MCP plus a deterministic authority middleware."""
from pathlib import Path
import argparse
import asyncio
import json
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def send_canvas_number(guard, arguments, send_keys):
    """Preserve the ImGui selection made by the preceding guarded Click."""
    for character in arguments["text"]:
        guard.recheck_canvas_keys(arguments)
        send_keys(character, interval=0.04, waitTime=0.05)
    guard.recheck_canvas_keys(arguments)
    send_keys("{Enter}", waitTime=0.05)


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
    from harness.native_save_policy import InputGuard, native_tools
    scope = json.loads((root / "scope.json").read_text())
    from fastmcp.server.middleware import Middleware
    from fastmcp.tools.base import ToolResult
    from mcp.types import TextContent
    from harness.native_authority import AuthorityController, validate_scope, attach_authority
    from harness.native_diagnostic_recovery import DIAGNOSTIC_SCENARIOS
    from harness.native_matrix import CANVAS_REPLACE_SCENARIOS, SAVE_CLEAR_SCENARIOS, UIA_HYBRID_SCENARIOS, UIA_SAVE_SCENARIO
    recovery_enabled = validate_scope(scope,
        json.loads((root.parent / "manifest.json").read_text()),
        json.loads((root.parent / "contract.json").read_text()),
        run_id=args.run_id, output_path=str(root / "projects/0001.3mf"))
    from windows_mcp import __main__ as original
    from windows_mcp.uia import SendKeys
    hybrid = scope["scenario"] in UIA_HYBRID_SCENARIOS
    if hybrid:
        from windows_mcp.uia import ControlFromHandle, ControlFromPoint, GetFocusedControl
        from harness.native_uia_hybrid import UiaHybridGuard
        guard = UiaHybridGuard(scope, root, ControlFromHandle, ControlFromPoint, GetFocusedControl, SendKeys)
    elif scope["scenario"] == UIA_SAVE_SCENARIO:
        from windows_mcp.uia import ControlFromHandle
        from harness.native_uia import UiaSaveGuard
        guard = UiaSaveGuard(scope, root, ControlFromHandle)
    else:
        guard = InputGuard(scope, root)

    def canvas_dispatch(arguments):
        send_canvas_number(guard, arguments, SendKeys)
        message = "Sent numeric keys and Enter to the bound canvas without re-clicking. Inspect the committed value."
        return ToolResult(content=[TextContent(type="text", text=message)],
                          structured_content={"result": message})

    class Authority(Middleware):
        def __init__(self):
            self.lock = asyncio.Lock()
            self.controller = AuthorityController(guard, root, args.run_id,
                recovery_enabled=recovery_enabled, diagnostic_enabled=scope["scenario"] in DIAGNOSTIC_SCENARIOS,
                canvas_dispatch=canvas_dispatch if scope["scenario"] in CANVAS_REPLACE_SCENARIOS else None,
                record_edit_frames=scope["scenario"] in SAVE_CLEAR_SCENARIOS)

        async def on_call_tool(self, context, call_next):
            async with self.lock:
                name, arguments = context.message.name, context.message.arguments or {}

                async def dispatch():
                    if ((hybrid or scope["scenario"] == UIA_SAVE_SCENARIO)
                            and (name == "Snapshot" or "target" in arguments)):
                        value = json.dumps(guard.perform(name, arguments), ensure_ascii=False)
                        return ToolResult(content=[TextContent(type="text", text=value)],
                                          structured_content={"result": value})
                    payload = await call_next(context)
                    if hybrid and name == "Screenshot" and not payload.is_error:
                        if sum(item.type == "image" for item in payload.content) != 1:
                            raise ValueError("native_uia_crop_missing")
                        guard.complete_view(arguments)
                    return payload

                payload, receipt = await self.controller.call(name, arguments, dispatch)
                if receipt["decision"] == "completed":
                    try:
                        return ToolResult(content=payload.content,
                            structured_content=attach_authority(payload.structured_content, receipt),
                            meta=payload.meta)
                    except Exception:
                        self.controller.abort("native_result_envelope_failed")
                        raise
                explanation = ("Input was NOT dispatched. Observe the current screen before correcting the numeric field."
                    if receipt["decision"] == "recoverable" else "Authority revoked. Stop this run.")
                return ToolResult(content=[TextContent(type="text", text=explanation)],
                                  structured_content={"authority": receipt}, is_error=True)

    original._build_mcp().add_middleware(Authority())
    original.main(["serve", "--transport", "streamable-http", "--host", "127.0.0.1",
                   "--port", "18789", "--stateless-http", "--no-control", "--tools",
                   ",".join(sorted(native_tools(scope["scenario"]))), "--config", str(root / "config.toml")])


if __name__ == "__main__":
    main()
