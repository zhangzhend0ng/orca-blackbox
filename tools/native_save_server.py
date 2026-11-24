"""Original pinned Windows-MCP plus a deterministic authority middleware."""
from pathlib import Path
import argparse
import asyncio
import json
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


from harness.canvas_input import send_canvas_number


def authority_refusal(receipt, window):
    result = {"authority": receipt}
    if receipt["decision"] != "recoverable":
        return "Authority revoked. Stop this run.", result
    if receipt.get("error_code") != "native_uia_refresh_required":
        return "Input was not dispatched. Observe the current screen before correcting the numeric field.", result
    hint = window.get("refresh_hint")
    if hint is None:
        return ("Input was not dispatched. Refresh with Snapshot. If the intended control is drawn, "
                "request its named Screenshot again before clicking."), result
    result["refresh_hint"] = hint
    if "target" in hint:
        selector = json.dumps(hint["target"], ensure_ascii=False, separators=(",", ":"))
        return (f"Input was not dispatched. Call Snapshot before any new input. If it still lists this target, "
                f"use {hint['tool']} with target={selector} ({hint['pattern']})."), result
    return (f"Input was not dispatched. Refresh with Snapshot, then request Screenshot with "
            f"region_name={hint['region_name']} before a new Click."), result


def with_native_edits(content, observation, text_block):
    message = ("Scoped writable native Edit observation. Match bounds to the visible field row. "
               "Each loc is a hit-tested absolute desktop pixel for that field. "
               + json.dumps(observation, separators=(",", ":")))
    return [text_block(type="text", text=message), *content]


def load_scope(root, run_id):
    from harness.native_authority import validate_scope

    scope = json.loads((root / "scope.json").read_text(encoding="utf-8"))
    recovery_enabled = validate_scope(scope,
        json.loads((root.parent / "manifest.json").read_text(encoding="utf-8")),
        json.loads((root.parent / "contract.json").read_text(encoding="utf-8")),
        run_id=run_id, output_path=str(root / "projects/0001.3mf"))
    return scope, recovery_enabled


def main():
    from harness import host_guard
    from harness.agent_protocol import valid_run_id
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    valid_run_id(args.run_id)
    # the guest, or a test machine that opted in (host_guard.allow_testbox)
    if not host_guard.real_execution_allowed():
        raise PermissionError("native server requires guest")
    root = REPO / "artifacts/v3" / args.run_id / "artifacts"
    from harness.native_save_policy import InputGuard, NATIVE_EDIT_OBSERVATION_SCENARIOS, native_tools
    from fastmcp.server.middleware import Middleware
    from fastmcp.tools.base import ToolResult
    from mcp.types import TextContent
    from harness.native_authority import AuthorityController, attach_authority
    from harness.native_diagnostic_recovery import DIAGNOSTIC_SCENARIOS
    from harness.native_matrix import CANVAS_REPLACE_SCENARIOS, SAVE_CLEAR_SCENARIOS, UIA_HYBRID_SCENARIOS, UIA_SAVE_SCENARIOS
    scope, recovery_enabled = load_scope(root, args.run_id)
    from windows_mcp import __main__ as original
    from windows_mcp.uia import SendKeys
    hybrid = scope["scenario"] in UIA_HYBRID_SCENARIOS
    if hybrid:
        from windows_mcp.uia import ControlFromHandle, ControlFromPoint
        from harness.native_uia_hybrid import UiaHybridGuard
        guard = UiaHybridGuard(scope, root, ControlFromHandle, ControlFromPoint)
    elif scope["scenario"] in UIA_SAVE_SCENARIOS:
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
                recovery_enabled=recovery_enabled, uia_refresh_enabled=hybrid,
                diagnostic_enabled=scope["scenario"] in DIAGNOSTIC_SCENARIOS,
                canvas_dispatch=canvas_dispatch if scope["scenario"] in CANVAS_REPLACE_SCENARIOS else None,
                record_edit_frames=scope["scenario"] in SAVE_CLEAR_SCENARIOS)

        async def on_call_tool(self, context, call_next):
            async with self.lock:
                name, arguments = context.message.name, context.message.arguments or {}

                async def dispatch():
                    if hybrid and guard.uses_process_message(name, arguments):
                        value = json.dumps(guard.click_drawn_process(arguments))
                        return ToolResult(content=[TextContent(type="text", text=value)],
                                          structured_content={"result": value})
                    if hybrid and name == "Screenshot" and guard.last_window.get("route") == "uia_popup":
                        value = json.dumps(guard.perform(name, arguments), ensure_ascii=False)
                        return ToolResult(content=[TextContent(type="text", text=value)],
                                          structured_content={"result": value, "popup_observation": True})
                    if ((hybrid or scope["scenario"] in UIA_SAVE_SCENARIOS)
                            and (name == "Snapshot" or {"target", "mix_role", "process_group"} & arguments.keys())):
                        value = json.dumps(guard.perform(name, arguments), ensure_ascii=False)
                        return ToolResult(content=[TextContent(type="text", text=value)],
                                          structured_content={"result": value})
                    if not hybrid or name != "Screenshot":
                        payload = await call_next(context)
                        if (scope["scenario"] in NATIVE_EDIT_OBSERVATION_SCENARIOS
                                and name in {"Screenshot", "Snapshot"} and not payload.is_error):
                            observed = guard.observe_native_edits()
                            fields = observed.get("fields")
                            guard.last_window["native_edit_observation"] = {
                                "available": fields is not None,
                                "field_count": len(fields or []),
                                "focused_count": sum(row["focused"] for row in (fields or [])),
                                "truncated": observed.get("truncated", False),
                            }
                            return payload.model_copy(update={
                                "content": with_native_edits(payload.content, observed, TextContent),
                            })
                        return payload
                    region = guard.capture_region()
                    message = context.message.model_copy(update={"arguments": {"region": region}})
                    payload = await call_next(context.copy(message=message))
                    if payload.is_error:
                        return payload
                    if sum(item.type == "image" for item in payload.content) != 1:
                        raise ValueError("native_uia_crop_missing")
                    guard.complete_view()
                    structured = dict(payload.structured_content or {}, crop_region=region,
                                      crop_region_name=guard.last_window["visual_fallback"])
                    return payload.model_copy(update={"structured_content": structured})

                payload, receipt = await self.controller.call(name, arguments, dispatch)
                if receipt["decision"] == "completed":
                    try:
                        return ToolResult(content=payload.content,
                            structured_content=attach_authority(payload.structured_content, receipt),
                            meta=payload.meta)
                    except Exception:
                        self.controller.abort("native_result_envelope_failed")
                        raise
                explanation, structured = authority_refusal(receipt, guard.last_window)
                return ToolResult(content=[TextContent(type="text", text=explanation)],
                                  structured_content=structured, is_error=True)

    original._build_mcp().add_middleware(Authority())
    original.main(["serve", "--transport", "streamable-http", "--host", "127.0.0.1",
                   "--port", "18789", "--stateless-http", "--no-control", "--tools",
                   ",".join(sorted(native_tools(scope["scenario"]))), "--config", str(root / "config.toml")])


if __name__ == "__main__":
    main()
