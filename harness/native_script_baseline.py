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
            # fa706g3 diagnosis 2026-11-22: the ironing SPEED row is NOT in
            # the Quality rebuild - ironing_speed ("Ironing speed", mm/s)
            # lives on the Speed tab other-layers group (PrintConfig.cpp:3618
            # + Tab.cpp:2433); tesseract reads the leading I as l, so match
            # 'roning speed' first. Flow (10%) and Spacing (0.15) already
            # equal the case targets (run 60237e59 readback note).
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["roning speed", "Ironing speed"], "value": "60"},
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
        "uia_param_bridge": [
            {"tab": "Quality", "tab_hint": "height", "op": "float", "label": "Bridge flow", "value": "1",
             "group": "Bridge"},
            {"op": "float", "label": "Bridge density", "value": "100", "group": "Bridge"},
            {"op": "checkbox", "label": "Thick", "value": True, "group": "Bridge"},
            {"op": "float", "label": "Max bridge length", "value": "30", "group": "Bridge"},
        ],
        "uia_param_first_speeds": [
            # Band evidence (run 5edba086): the Speed page rows read
            # "First layer speed / First layer infill / Initial layer travel";
            # travel is a coFloatsOrPercent stored with '%' (preset "80%").
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["First layer speed", "Initial layer speed"], "value": "30",
             "group": "Initial layer"},
            {"op": "float", "label": ["First layer infill", "Initial layer infill"], "value": "40",
             "group": "Initial layer"},
            {"op": "float", "label": ["Initial layer travel", "First layer travel"], "value": "150%",
             "group": "Initial layer"},
        ],
        "uia_param_feature_speeds": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float", "label": "Outer wall", "value": "100"},
            {"op": "float", "label": "Inner wall", "value": "150"},
            {"op": "float", "label": ["Sparse infill", "Infill"], "value": "200"},
            {"op": "float", "label": "Top surface", "value": "120"},
            {"op": "float", "label": ["Small perimeter threshold", "Small perimeter linewidth"], "value": "10"},
            {"op": "float", "label": ["Small perimeter speed", "Small perimeter"], "value": "50"},
        ],
        "uia_param_fuzzy": [
            {"tab": "Quality", "tab_hint": "height", "op": "rowcombo", "label": "Fuzzy skin",
             "target": "All external walls", "group": "Fuzzy"},
            {"op": "float", "label": "point distance", "value": "0.6", "group": "Fuzzy"},
            {"op": "float", "label": "thickness", "value": "0.3", "group": "Fuzzy"},
        ],
        "uia_param_infill_combo": [
            {"tab": "Strength", "tab_hint": "loops", "op": "float", "label": "Density", "value": "20",
             "group": "Infill"},
            {"op": "rowcombo", "label": "Sparse infill pattern", "target": "Gyroid", "group": "Infill"},
            {"op": "float", "label": "Infill direction", "value": "45", "group": "Infill"},
            {"op": "float", "label": "overlap", "value": "15"},
            {"op": "rowcombo", "label": "Gap fill", "target": "Everywhere"},
        ],
        # Feishu #264: detect checkbox lives on Quality; the five band speeds
        # are one "Overhang speed" row with five inline Edits (field 0..4).
        "uia_param_overhang_speeds": [
            {"tab": "Quality", "tab_hint": "height", "op": "checkbox", "label": "Detect overhang",
             "value": True},
            {"tab": "Speed", "tab_hint": "speed", "op": "checkbox", "label": "Slow down",
             "value": True, "group": "Overhang"},
            {"op": "float", "label": "Overhang speed", "value": "40", "group": "Overhang", "field": 0},
            {"op": "float", "label": "Overhang speed", "value": "30", "group": "Overhang", "field": 1},
            {"op": "float", "label": "Overhang speed", "value": "20", "group": "Overhang", "field": 2},
            {"op": "float", "label": "Overhang speed", "value": "10", "group": "Overhang", "field": 3},
            {"op": "float", "label": "Overhang speed", "value": "5", "group": "Overhang", "field": 4},
        ],
        "uia_param_accelerations": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["Normal printing", "Default acceleration"], "value": "3000",
             "group": "Acceleration"},
            {"op": "float", "label": ["Outer wall", "Outer wall acceleration"], "value": "2000",
             "group": "Acceleration"},
            {"op": "float", "label": ["Inner wall", "Inner wall acceleration"], "value": "4000",
             "group": "Acceleration"},
            {"op": "float", "label": ["Sparse infill", "Sparse infill acceleration"], "value": "5000",
             "group": "Acceleration"},
            {"op": "float", "label": ["Initial layer", "Initial layer acceleration"], "value": "500",
             "group": "Acceleration"},
            {"op": "float", "label": ["Travel", "Travel acceleration"], "value": "8000",
             "group": "Acceleration"},
        ],
        "uia_param_skirt": [
            {"tab": "Others", "op": "float", "label": "Skirt loops", "value": "3", "group": "Skirt"},
            {"op": "float", "label": "Skirt distance", "value": "5", "group": "Skirt"},
            {"op": "float", "label": "Skirt height", "value": "2", "group": "Skirt"},
            # rowcombo on this two-item enum popup twice no-oped (saved
            # draft_shield stayed 'disabled', runs a4396ae2/2da24319); the
            # value-anchored combo op is the proven path (#259 ironing type).
            {"op": "combo", "current": "Disabled", "target": "Enabled", "group": "Skirt"},
        ],
        "uia_param_brim": [
            # Brim-width Edit renders DISABLED under auto_brim (runs
            # c84c9bd9/a97ed9b7: param_uia_field 0 matches); pick the type
            # first so the row edits enable.
            {"tab": "Others", "op": "rowcombo", "label": "Brim type", "target": "Outer only",
             "group": "Brim"},
            {"op": "float", "label": "Brim width", "value": "5", "group": "Brim"},
            {"op": "float", "label": "Brim object gap", "value": "0.2", "group": "Brim"},
        ],
        # Feishu #276 (snapshot line 195): the table's filament/machine-scope
        # keys (filament_max_volumetric_speed, machine_max_speed_x) are not
        # reachable from the process panel and stay out of the ops/values.
        "uia_param_speed_limits": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["Layer height", "layer height"], "value": "0.2"},
            {"op": "float", "label": ["Outer wall line width", "Outer wall"], "value": "0.42",
             "group": "Advanced"},
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["Outer wall speed", "Outer wall"], "value": "700"},
        ],
        # Feishu #277 (line 196): enable/threshold/type; the two '0' flags are
        # already at target in the fixture config - no ops for them.
        "uia_param_support_basic": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox", "label": "Enable",
             "value": True, "group": "Support"},
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "float", "label": ["Threshold angle", "Threshold"], "value": "45", "group": "Support"},
        ],
        # Feishu #278 (line 197): raft fields, raft_layers first so the rest
        # of the group settles.
        "uia_param_raft": [
            {"tab": "Support", "tab_hint": "support", "op": "float", "label": ["Raft layers", "Raft"],
             "value": "3", "group": "Raft"},
            {"op": "float", "label": ["Raft contact Z distance", "Raft contact distance",
                                      "Raft contact"], "value": "0.2", "group": "Raft"},
            {"op": "float", "label": ["Raft expansion"], "value": "5", "group": "Raft"},
            {"op": "float", "label": ["Raft first layer density", "first layer density"],
             "value": "100", "group": "Raft"},
            {"op": "float", "label": ["Raft first layer expansion", "first layer expansion"],
             "value": "5", "group": "Raft"},
        ],
        # Feishu #279 (line 198): the row is painted 'Support/Interface
        # filament' (two combos); single-word label so phrase-join OCR can
        # match it. Interface already 0 - no second op.
        "uia_param_support_filament": [
            {"tab": "Support", "tab_hint": "support", "op": "rowcombo", "label": "filament",
             "target": "1", "group": "Support"},
        ],
        # Feishu #292 (line 211): clearance rows appear once by-object is set.
        "uia_param_by_object": [
            {"tab": "Others", "tab_hint": "special", "op": "combo", "current": "By layer",
             "target": "By object", "group": "Special mode"},
            {"op": "float", "label": ["Extruder clearance radius", "clearance radius"],
             "value": "20", "group": "Special mode"},
            {"op": "float", "label": ["Extruder clearance height to rod", "height to rod"],
             "value": "30", "group": "Special mode"},
        ],
        # Feishu #293 (line 212): spiral on Others, then the seam combo on
        # Quality (the m5h quality-enums route).
        "uia_param_spiral_vase": [
            {"tab": "Others", "tab_hint": "special", "op": "checkbox", "label": "Spiral",
             "value": True, "group": "Special mode"},
            {"tab": "Quality", "tab_hint": "height", "op": "combo", "current": "Aligned",
             "target": "nearest", "group": "Seam"},
        ],
        # Feishu #294 (line 213): slicing_mode already 'regular' in the
        # fixture config - only the timelapse selector is driven.
        "uia_param_timelapse": [
            {"tab": "Others", "tab_hint": "special", "op": "combo", "current": "None",
             "target": "Smooth", "group": "Special mode"},
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
