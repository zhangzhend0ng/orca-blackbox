"""Fixed script actions for the two native-save comparison targets."""
from decimal import Decimal
from pathlib import Path
import re
import sys

from .agent_protocol import ProtocolError
from .native_matrix import UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO


def edit_layer(ui):
    # The shared Quality start leaves the option viewport at the top.
    from .process_panel import float_edits_in_view

    edits = ui.wait(lambda: float_edits_in_view(ui.app), 16)
    if (len(edits) < 2 or any(not ui.owned(hwnd) or Decimal(value) != Decimal("0.4")
                              for _, hwnd, value in edits[:2])
            or edits[0][0][1] >= edits[1][0][1]):
        raise ProtocolError("script_layer_fields_not_as_expected")
    rect, edit_hwnd, _ = edits[0]
    origin_x, origin_y = ui.wu.client_to_screen(ui.app.hwnd, 0, 0)
    x, y = (rect[0] + rect[2]) // 2 - origin_x, (rect[1] + rect[3]) // 2 - origin_y
    receipt = ui.edit(x, y, "0.24")
    if receipt["target_hwnd"] != edit_hwnd or Decimal(receipt["after_text"]) != Decimal("0.24"):
        raise ProtocolError("script_layer_readback")


def move_x(ui, canvas):
    # Reuse the existing hand-authored m6a locators. The only change to the
    # recipe is the +10 mm target relative to the trusted cube fixture.
    # Use the source tree, regardless of the output root's layout.
    tests = Path(__file__).resolve().parents[1] / "tests"
    for folder in (tests, tests / "engine", tests / "mixing"):
        sys.path.insert(0, str(folder))
    from m4e_mixing_paint import BAR_Y, find_model_centroid, find_slot
    from m6a_transform_verify import position_row_wait
    from .pilot_transform import _expected_fixture

    def guard():
        ui.guard()
        if (ui.wu.user32.GetForegroundWindow() != ui.app.hwnd
                or not ui.owned(canvas) or not ui.wu.user32.IsChild(ui.app.hwnd, canvas)
                or ui.wu.window_class(canvas) != "wxGLCanvas"
                or not ui.wu.user32.IsWindowEnabled(canvas)):
            raise ProtocolError("script_canvas_target_changed")

    def click(loc):
        guard()
        sx, sy = ui.wu.client_to_screen(ui.app.hwnd, *loc)
        if ui.wu.window_from_screen_point(sx, sy) != canvas:
            raise ProtocolError("script_canvas_point_not_owned")
        ui.wu.real_click_screen(sx, sy)

    guard()
    click(ui.wait(lambda: find_model_centroid(ui.app), 15))
    ui.pause(1.2)
    move, _ = find_slot(ui.app, lambda words: bool(re.search(r"\bmove\b", words)))
    if move is None:
        raise ProtocolError("script_move_tool_missing")
    click((move, BAR_Y))
    ui.pause(2.5)
    box, current = position_row_wait(ui.app, timeout_s=12)
    fixture = (ui.artifacts / "input/fixture.3mf").read_bytes()
    _, wanted, original = _expected_fixture(fixture, lambda: False)
    if box is None or Decimal(current.replace(",", ".")) != original[9]:
        raise ProtocolError("script_canvas_original_x")
    click(box)
    ui.pause(0.6)
    # Deliver to the checked GL recipient, never a fallback main HWND.
    for char in "\b" * (len(current) + 2) + format(wanted[9], "f"):
        guard()
        ui.wu._send_msg(canvas, 0x0102, ord(char), 0)  # WM_CHAR
        ui.pause(0.05)
    guard()
    ui.wu._send_msg(canvas, 0x0100, 0x0D, 0)  # WM_KEYDOWN / VK_RETURN
    guard()
    ui.wu._send_msg(canvas, 0x0102, 0x0D, 0)
    _, actual = position_row_wait(ui.app, expect=format(wanted[9], "f"), timeout_s=12)
    if not actual or Decimal(actual.replace(",", ".")) != wanted[9]:
        raise ProtocolError("script_canvas_readback")


def edit_project(ui, scenario, canvas):
    if scenario == UIA_LAYER_SCENARIO:
        edit_layer(ui)
    elif scenario == UIA_CANVAS_SCENARIO:
        move_x(ui, canvas)
    else:
        raise ProtocolError("script_comparison_scenario")
