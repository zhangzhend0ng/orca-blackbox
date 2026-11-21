"""Fixed script actions for the two native-save comparison targets."""
from decimal import Decimal
from pathlib import Path
import re
import sys

from .agent_protocol import ProtocolError, read_json
from .native_matrix import (UIA_CANVAS_SCENARIO, UIA_LAYER_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO,
    UIA_MIX_RECIPES, UIA_MOVE_LAYER, UIA_PROCESS_COMBO, UIA_QUALITY_ENUMS)


def edit_layer(ui, value="0.24"):
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
    receipt = ui.edit(x, y, value)
    if receipt["target_hwnd"] != edit_hwnd or Decimal(receipt["after_text"]) != Decimal(value):
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


def move_x(ui, canvas, *, original_x=None, delta_mm=10):
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
        # The existing m6a path lets ImGui observe the cursor on a render frame.
        if not ui.wu.user32.SetCursorPos(sx, sy):
            raise ProtocolError("script_canvas_cursor_not_positioned")
        ui.pause(0.2)
        guard()
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
    if original_x is None:
        fixture = (ui.artifacts / "input/fixture.3mf").read_bytes()
        _, _, matrix = _expected_fixture(fixture, lambda: False)
        original_x = matrix[9]
    if box is None or Decimal(current.replace(",", ".")) != original_x:
        raise ProtocolError("script_canvas_original_x")
    click(box)
    ui.pause(0.6)
    expected = format(original_x + delta_mm, "f")
    scope = read_json(ui.artifacts / "scope.json")
    screen_point = ui.wu.client_to_screen(ui.app.hwnd, *box)
    _type_canvas_number(ui, scope, screen_point, expected)
    ui.pause(0.6)
    _, actual = position_row_wait(ui.app, expect=expected, timeout_s=12)
    print(f"[native-script] Position X readback: before={current[:48]!r} expected={expected!r} actual={(actual or '')[:48]!r}")
    # The ImGui overlay can close or OCR can miss the value after commit.
    # The common saved-project and actual-extrusion checks decide success.
    return {"before": current, "submitted": expected, "observed_after": actual}


def edit_process_combo(ui):
    from . import process_panel as pp

    app = ui.app
    ui.main_input()
    pp.ensure_advanced(app, want=True)
    if not pp.click_tab(app, "Quality", "height"):
        raise ProtocolError("process_combo_quality_tab")
    edit_layer(ui, "0.3")
    ui.pause(6)
    ui.main_input()
    if not pp.click_tab(app, "Strength", "loops"):
        raise ProtocolError("process_combo_strength_tab")
    updated, _, _ = pp.set_option_float(app, "density", "30", group_substr="Infill")
    if not updated:
        raise ProtocolError("process_combo_infill_edit")
    ui.pause(6)
    ui.main_input()
    if not pp.click_tab(app, "Support", "support"):
        raise ProtocolError("process_combo_support_tab")
    enabled, _ = pp.set_option_checkbox(app, "Enable", True, group_substr="Support")
    if enabled is not True:
        raise ProtocolError("process_combo_support_checkbox")
    ui.pause(6)
    ui.main_input()
    _, updated = pp.set_combo_by_popup(app, "Tree", "Normal", log="[native-script process combo]")
    if not updated:
        raise ProtocolError("process_combo_support_type")


def edit_quality_enums(ui):
    # Retain m5h's sidebar order and rebuild protection.
    from . import process_panel as pp

    app = ui.app
    ui.main_input()
    pp.ensure_advanced(app, want=True)
    if not pp.click_tab(app, "Quality", "height") or not pp.scroll_group_into_view(app, "Ironing", timeout_s=45):
        raise ProtocolError("quality_enums_ironing_group")
    located, _ = pp.set_combo_by_popup(app, ("no", "ironing"), "topmost", log="[m5h replay baseline]", psm=6)
    if not located:
        raise ProtocolError("quality_enums_ironing_choice")
    pp.neutralize_focus(app)
    ui.pause(12)
    ui.main_input()
    if (not pp.click_tab(app, "Strength", "loops") or not pp.click_tab(app, "Quality", "height")
            or not pp.scroll_group_into_view(app, "Seam", timeout_s=45)):
        raise ProtocolError("quality_enums_seam_group")
    located, _ = pp.set_combo_by_popup(app, "Aligned", "random", log="[m5h replay baseline]", psm=6)
    if not located:
        raise ProtocolError("quality_enums_seam_choice")
    pp.neutralize_focus(app)
    ui.pause(12)


def add_mix_recipes(ui, *, census=False):
    tests = Path(__file__).resolve().parents[1] / "tests"
    sys.path.insert(0, str(tests / "mixing"))
    from m4i_mixing_slice import register_scheme, sidebar_entries

    for mode in ("Ratio", "Gradient"):
        ui.main_input()
        observe = None
        if census:
            from tools.native_mix_census import observer
            observe = observer(ui, mode)
        ok, _ = register_scheme(ui.app, mode, len(sidebar_entries(ui.app)), observe=observe)
        if not ok:
            raise ProtocolError("mix_recipe_registration:" + mode)


def edit_param_layer_pair(ui):
    """Feishu #254: regular 0.20 mm + initial layer 0.25 mm on Quality."""
    from .process_panel import float_edits_in_view

    ui.main_input()
    edit_layer(ui, "0.2")
    ui.pause(1.5)
    ui.main_input()
    # 'First layer height' sits directly under Layer height on the same
    # Quality view; its painted label row carries no Edit in the calibrated
    # value column (runs 35211f/d70ef26), but float_edits_in_view sees the
    # field itself - positional edit like edit_layer, second row.
    edits = ui.wait(lambda: float_edits_in_view(ui.app), 16)
    if len(edits) < 2 or Decimal("0.4") != Decimal(edits[1][2]):
        raise ProtocolError("param_layer_pair_initial_field")
    rect, edit_hwnd, _ = edits[1]
    origin_x, origin_y = ui.wu.client_to_screen(ui.app.hwnd, 0, 0)
    x, y = (rect[0] + rect[2]) // 2 - origin_x, (rect[1] + rect[3]) // 2 - origin_y
    receipt = ui.edit(x, y, "0.25")
    if receipt["target_hwnd"] != edit_hwnd or Decimal(receipt["after_text"]) != Decimal("0.25"):
        raise ProtocolError("param_layer_pair_initial_readback")
    ui.pause(6)
    ui.main_input()


def edit_param_cases(ui, scenario):
    """Feishu 常用工艺参数 supplement cases (declarative process-panel ops)."""
    from .param_case_lib import run_ops

    ops = {
        "uia_param_ironing_top": [
            {"tab": "Quality", "tab_hint": "height", "op": "combo", "current": "No ironing",
             "target": "Topmost surface", "group": "Ironing"},
            # Flow (10%) and Spacing (0.15) already equal the case targets;
            # typing into the ratio-clamped Flow spin corrupted it (run
            # 60237e59 read back '2') - only Speed needs an edit.
            {"op": "float", "label": ["Speed", "Ironing speed", "speed"], "value": "60", "group": "Ironing"},
        ],
        "uia_param_wall_thin": [
            {"tab": "Strength", "tab_hint": "loops", "op": "float", "label": "Wall loops", "value": "4"},
            {"op": "checkbox", "label": "Detect", "value": True},
        ],
        "uia_param_shells_pattern": [
            {"tab": "Strength", "tab_hint": "loops", "op": "float", "label": "Top shell layers", "value": "5"},
            {"op": "float", "label": "Bottom shell layers", "value": "3"},
            {"op": "rowcombo", "label": "Top surface pattern", "target": "Concentric"},
            {"op": "rowcombo", "label": "Bottom surface pattern", "target": "Rectilinear"},
        ],
        "uia_param_infill_combo": [
            {"tab": "Strength", "tab_hint": "loops", "op": "float", "label": "Density", "value": "20",
             "group": "Infill"},
            {"op": "rowcombo", "label": "Sparse infill pattern", "target": "Gyroid", "group": "Infill"},
            {"op": "float", "label": "Infill direction", "value": "45", "group": "Infill"},
            {"op": "float", "label": "overlap", "value": "15"},
            {"op": "rowcombo", "label": "Gap fill", "target": "Everywhere"},
        ],
    }.get(scenario)
    if ops is None:
        raise ProtocolError("param_case_ops:" + scenario)
    try:
        run_ops(ui, ops)
    except Exception:
        import traceback
        traceback.print_exc()
        raise


def assign_filament_slot2(ui):
    """Deterministic slot2 positive control: the object context menu's
    Change Filament submenu (the same route m7j_change_filament has run
    GREEN since 09-08), picking the second physical filament row."""
    import ctypes
    from types import SimpleNamespace

    tests = Path(__file__).resolve().parents[1] / "tests"
    sys.path.insert(0, str(tests))
    import m7_common as m7

    session = SimpleNamespace(hwnd=ui.app.hwnd, pid=ui.app.pid)
    ui.main_input()
    if not m7.select_model(session):
        raise ProtocolError("slot2_select_model")
    menu = m7.open_context_menu(session, where="model")
    if not menu:
        raise ProtocolError("slot2_context_menu")
    hwnd, hmenu = menu
    got = m7.click_menu_row(session, hwnd, hmenu, "change filament", nested=True)
    if not got:
        m7.dismiss_menus(session)
        raise ProtocolError("slot2_change_filament_submenu")
    _idx, (shwnd, shmenu) = got
    rows = [(i, label) for i, label in m7.list_menu(shmenu)
            if label.strip() and label.lower() != "default"]
    if len(rows) < 2:
        m7.dismiss_menus(session)
        raise ProtocolError("slot2_filament_rows:" + str([l for _i, l in rows]))
    slot2_index, slot2_label = rows[1]
    state = ctypes.WinDLL("user32").GetMenuState(shmenu, slot2_index, 0x400)
    if state & 0x8:  # already checked - the fixture would be wrong
        m7.dismiss_menus(session)
        raise ProtocolError("slot2_row_already_checked")
    m7.click_menu_row(session, shwnd, shmenu, slot2_label)
    ui.pause(2.0)
    ui.main_input()


def edit_project(ui, scenario, canvas, *, mix_census=False):
    if scenario in {UIA_LAYER_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO}:
        if scenario == UIA_LAYER_STRENGTH_SCENARIO:
            quality = ui.wait(lambda: ui.named_child("Quality"), 15)
            ui.click_rect(quality[1])
            ui.pause(2)
        edit_layer(ui)
    elif scenario == UIA_CANVAS_SCENARIO:
        move_x(ui, canvas)
    elif scenario == UIA_PROCESS_COMBO:
        edit_process_combo(ui)
    elif scenario == UIA_QUALITY_ENUMS:
        edit_quality_enums(ui)
    elif scenario == UIA_MOVE_LAYER:
        edit_layer(ui)
        move_x(ui, canvas)
    elif scenario == UIA_MIX_RECIPES:
        add_mix_recipes(ui, census=mix_census)
    elif scenario == "pilot_material":
        assign_filament_slot2(ui)
    elif scenario == "uia_param_layer_pair":
        edit_param_layer_pair(ui)
    elif scenario.startswith("uia_param_"):
        edit_param_cases(ui, scenario)
    else:
        raise ProtocolError("script_comparison_scenario")
