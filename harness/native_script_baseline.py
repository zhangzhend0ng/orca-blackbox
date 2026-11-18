"""Fixed script actions for the two native-save comparison targets."""
from decimal import Decimal
from pathlib import Path
import re
import sys

from .agent_protocol import ProtocolError, read_json
from .native_matrix import UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO


def edit_layer(ui):
    # Quality is open before locating its regular layer height Edit.
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


def _type_canvas_number(ui, scope, screen_point, text):
    from . import mix_dialog_util as mdu
    from .canvas_input import send_canvas_number
    from .native_save_policy import InputGuard

    def send_key(key, **_):
        ui.guard()
        if key == "{Enter}":
            mdu._send_keys([(mdu.VK_RETURN, False), (mdu.VK_RETURN, True)])
            ui.pause(0.05)
        else:
            mdu._send_chars(key)

    send_canvas_number(InputGuard(scope, ui.artifacts), {"loc": list(screen_point), "text": text}, send_key)


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
        if ui.wu.real_click_screen(sx, sy) != 2:
            raise ProtocolError("script_canvas_click_not_dispatched")

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
    expected = format(wanted[9], "f")
    scope = read_json(ui.artifacts / "scope.json")
    screen_point = ui.wu.client_to_screen(ui.app.hwnd, *box)
    _type_canvas_number(ui, scope, screen_point, expected)
    _, actual = position_row_wait(ui.app, expect=expected, timeout_s=12)
    print(f"[native-script] Position X readback: before={current[:48]!r} expected={expected!r} actual={(actual or '')[:48]!r}")
    if not actual or Decimal(actual.replace(",", ".")) != wanted[9]:
        raise ProtocolError("script_canvas_readback")


def edit_project(ui, scenario, canvas):
    if scenario in {UIA_LAYER_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO}:
        if scenario == UIA_LAYER_STRENGTH_SCENARIO:
            quality = ui.wait(lambda: ui.named_child("Quality"), 15)
            ui.click_rect(quality[1])
            ui.pause(2)
        edit_layer(ui)
    elif scenario == UIA_CANVAS_SCENARIO:
        move_x(ui, canvas)
    else:
        raise ProtocolError("script_comparison_scenario")
