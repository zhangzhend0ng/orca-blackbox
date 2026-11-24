import asyncio
import json
from types import SimpleNamespace

import pytest

from harness.native_authority import AuthorityController
from harness.native_save_policy import InputGuard, visible_native_edits
from tools.native_save_server import with_native_edits


def test_writable_edit_observation_shares_input_hit_test_and_reaches_mcp_content():
    def bounds(hwnd):
        return [20, 30 * hwnd, 100, 30 * hwnd + 20]

    wu = SimpleNamespace(
        _window_pid=lambda hwnd: 23 if hwnd == 4 else 17,
        window_class=lambda hwnd: "wxWindowNR" if hwnd == 5 else "Edit",
        window_rect=bounds,
        window_from_screen_point=lambda x, y: 98 if y // 30 == 7 else y // 30,
    )
    gui = SimpleNamespace(
        IsWindowVisible=lambda hwnd: hwnd != 6,
        IsWindowEnabled=lambda hwnd: hwnd != 8,
        GetWindowLong=lambda hwnd, index: {9: 0x800, 10: 0x20}.get(hwnd, 0),
    )
    observation = visible_native_edits(wu, gui, [10, 4, 8, 2, 7, 9, 1, 5, 6], 2, 17)
    assert observation == {"fields": [
        {"bounds": [20, 30, 100, 50], "loc": [60, 40], "focused": False},
        {"bounds": [20, 60, 100, 80], "loc": [60, 70], "focused": True},
    ], "truncated": False}
    image = {"type": "image", "data": "original"}
    rendered, retained = with_native_edits([image], observation, dict)
    assert retained is image and rendered["type"] == "text"
    assert json.loads(rendered["text"].split("field. ", 1)[1]) == observation


@pytest.mark.parametrize(("hwnd", "text", "expected"), [
    (4, "700", "native_target_not_owned"),
    (5, "700", "native_type_requires_owned_edit"),
    (6, "701", "native_type_text_rejected"),
])
def test_native_observation_does_not_authorize_type(tmp_path, monkeypatch, hwnd, text, expected):
    wu = SimpleNamespace(
        window_from_screen_point=lambda x, y: hwnd,
        _window_pid=lambda window: 23 if window == 4 else 17,
        window_class=lambda window: "wxWindowNR" if window == 5 else "Edit",
    )
    scope = {"scenario": "compare_276_quality", "app_pid": 17, "output_path": "0001.3mf"}
    guard = InputGuard(scope, tmp_path)
    monkeypatch.setattr(guard, "owned_foreground", lambda: (wu, 1))
    controller = AuthorityController(guard, tmp_path, "0" * 32)

    async def dispatch():
        pytest.fail("invalid Type reached dispatch")

    _, receipt = asyncio.run(controller.call("Type", {"loc": [60, 40], "text": text}, dispatch))
    assert receipt["decision"] == "fatal"
    assert receipt["dispatched"] is False
    assert receipt["error_code"] == expected
