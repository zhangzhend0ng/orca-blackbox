import asyncio
import ctypes
import json
import sys
from types import SimpleNamespace

import pytest

from harness.native_authority import AuthorityController
from harness.native_save_policy import InputGuard
from tools.native_save_server import with_native_edits


def test_writable_edit_observation_reaches_mcp_content_in_minimal_environment(tmp_path, monkeypatch):
    for module in ("harness.process_panel", "win32gui", "pywintypes"):
        monkeypatch.setitem(sys.modules, module, None)

    def bounds(hwnd):
        return [20, 30 * hwnd, 100, 30 * hwnd + 20]

    def focus(thread, info_pointer):
        assert thread.value == 3
        info = info_pointer._obj
        assert info.cbSize == ctypes.sizeof(info)
        info.hwndFocus = 2
        return True

    def children(hwnd, callback, lparam):
        assert hwnd.value == 19
        for child in [10, 4, 8, 2, 7, 9, 1, 5, 6, 11]:
            assert callback(child, lparam)

    gui = SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd, pid: 3,
        GetGUIThreadInfo=focus,
        EnumChildWindows=children,
        IsWindowVisible=lambda hwnd: hwnd.value != 6,
        IsWindowEnabled=lambda hwnd: hwnd.value != 8,
        GetWindowLongW=lambda hwnd, index: {9: 0x800, 10: 0x20, 11: 0}.get(hwnd.value, 0x10000000),
    )
    wu = SimpleNamespace(
        user32=gui,
        WNDENUMPROC=lambda callback: callback,
        _window_pid=lambda hwnd: 23 if hwnd == 4 else 17,
        window_class=lambda hwnd: "wxWindowNR" if hwnd == 5 else "Edit",
        window_rect=bounds,
        window_from_screen_point=lambda x, y: 98 if y // 30 == 7 else y // 30,
    )
    guard = InputGuard({"app_pid": 17}, tmp_path)
    monkeypatch.setattr(guard, "owned_foreground", lambda: (wu, 19))
    observation = guard.observe_native_edits()
    assert observation == {"fields": [
        {"bounds": [20, 30, 100, 50], "loc": [60, 40], "focused": False},
        {"bounds": [20, 60, 100, 80], "loc": [60, 70], "focused": True},
    ], "truncated": False}
    image = {"type": "image", "data": "original"}
    rendered, retained = with_native_edits([image], observation, dict)
    assert retained is image and rendered["type"] == "text"
    assert json.loads(rendered["text"].split("field. ", 1)[1]) == observation

    foreground = iter([19, 20])
    monkeypatch.setattr(guard, "owned_foreground", lambda: (wu, next(foreground)))
    assert guard.observe_native_edits() == {"unavailable": True}


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
