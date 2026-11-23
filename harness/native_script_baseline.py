"""Fixed script actions for the two native-save comparison targets."""
from decimal import Decimal
from pathlib import Path
import re
import sys

from .agent_protocol import STD_SCENARIO, STD_TARGETS, ProtocolError, base_scenario, read_json
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


# App config a scenario needs beyond profile.MINIMAL_CONF, merged when the
# edit session's profile is seeded (tools/native_save_guest.py ->
# ProjectUI(conf_extra=...) -> profile.seed_profile). A scenario that needs
# nothing must not be listed: the conf is part of the run's conditions and
# is written into the worker report.
# 2026-11-24 (#296): gcode_add_line_number is comDevelop - the row exists
# only while the app runs in develop mode (GUI_App.cpp:6564-6566: mode
# "develop" -> comDevelop; the page's Advanced switch only reaches
# comAdvanced). It cannot be on for every scenario: develop mode adds rows
# to every page and the labels are calibrated on the default pages.
# The key lives in the conf's "app" section (the app's own dump:
# "app": {..., "user_mode": "advanced", ...}). At the top level the app never
# read it and started in SIMPLE mode - fa run 2adcf5cd: five tabs, summary
# rows, pages that do not scroll, conf 'simple' afterwards.
DEVELOP = {"app": {"user_mode": "develop"}}
SCENARIO_CONF = {
    "uia_param_gcode_output": DEVELOP,
    "uia_param_census_develop": DEVELOP,
}

# The full per-scenario op table (moved to module level so
# tools/check_ops_against_atlas.py can validate labels offline).
PARAM_OPS = {        "uia_param_ironing_top": [
            # 2026-11-22 run 1c5b910c: the row WAS on-band ('lroning type ~
            # No ironing') but single-word containment can never match the
            # two-word painted value - use the word-SEQUENCE locate tuple;
            # the popup match is also word-level, so the target must be one
            # OCR word ("Topmost" is unique in this popup).
            {"tab": "Quality", "tab_hint": "height", "op": "combo",
             "current": ("No", "ironing"), "target": "Topmost", "group": "Ironing"},
            # fa706g3 diagnosis 2026-11-22: the ironing SPEED row is NOT in
            # the Quality rebuild - ironing_speed ("Ironing speed", mm/s)
            # lives on the Speed tab other-layers group (PrintConfig.cpp:3618
            # + Tab.cpp:2433); tesseract reads the leading I as l, so match
            # 'roning speed' first. Flow (10%) and Spacing (0.15) already
            # equal the case targets (run 60237e59 readback note).
            # 2026-11-22 run 74c30ba5: multi-word variants are PREFIX
            # matched, so neither "roning speed" nor "Ironing speed" can hit
            # the OCR misread "lroning speed" - the single-word containment
            # variant "roning" matches it (substring), unique on the Speed
            # page. The combo step is PROVEN: this run rebuilt the whole
            # Ironing group (type/Pattern/flow/spacing/inset/angle).
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["roning", "Ironing speed"], "value": "60",
             "group": "Other layers speed"},
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
        # 2026-11-23 atlas + 2.3.5 census: the group is 'Bridging' (the wrong
        # title made every op wheel for 420s, run eacfc6ff); the density row
        # is 'External bridge density'; 'Max bridge length' has no row on
        # the page (like raft_expansion) - op and value dropped.
        "uia_param_bridge": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["^Bridge flow", "flow"], "value": "1", "group": "Bridging"},
            {"op": "float", "label": ["External bridge density", "density"], "value": "100",
             "group": "Bridging"},
            {"op": "checkbox", "label": "Thick", "value": True, "group": "Bridging"},
        ],
        "uia_param_first_speeds": [
            # Band evidence (run 5edba086): the Speed page rows read
            # "First layer speed / First layer infill / Initial layer travel";
            # travel is a coFloatsOrPercent stored with '%' (preset "80%").
            # The group 'Initial layer speed' is the page's FIRST group: at
            # the page top its title rests above the visible band, so
            # scroll_group_into_view could never satisfy its in-band test
            # and wheeled for 2 x 420s per failed op - the real reason every
            # #270 run looked wedged.
            # 2026-11-24: on the 2.4.0 page the first row's label is 'First
            # layer' (row fixture: 'First layer 35 mm/s'); 'First layer speed'
            # is the TITLE above it. run f96dbc0b passed because the older
            # engine took that title line for the row and 'below' its Edit -
            # the row's own Edit, 34px under the title. The engine skips
            # title lines since r3, so the row is anchored by its value
            # first ('First layer 35', #272 recipe) and by its label second
            # ('First layer' also starts 'First layer infill' - the scan
            # goes down from the group top and meets this row first).
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["^First layer 35", "^First layer"], "value": "30",
             "group": "First layer speed"},
            {"op": "float", "label": "^First layer infill", "value": "40",
             "group": "First layer speed"},
            {"op": "float", "label": "^Initial layer travel", "value": "150%",
             "group": "First layer speed"},
        ],
        # 2026-11-23: the group is spelled 'First layer speed' on the 2.4.0
        # page (census c101c0f4), not 'Initial layer' as in the source atlas;
        # with the wrong name scroll_group_into_view wheeled 68 notches away
        # and only the ungrouped fallback scan found the rows. The title
        # reads exactly like its first row's label; the engine no longer
        # takes a title line for a row (on_title_line).
        # 2026-11-23: rows anchored to the line start and confined to the
        # 'Other layers speed' group - the same labels exist in the
        # Acceleration and Jerk groups (census + screenshot f0e683fb); the
        # threshold row is 'Small perimeters threshold' (plural).
        "uia_param_feature_speeds": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float", "label": "^Outer wall",
             "value": "100", "group": "Other layers speed"},
            {"op": "float", "label": "^Inner wall", "value": "150", "group": "Other layers speed"},
            {"op": "float", "label": "^Sparse infill", "value": "200", "group": "Other layers speed"},
            {"op": "float", "label": "^Top surface", "value": "120", "group": "Other layers speed"},
            {"op": "float", "label": ["^Small perimeters threshold", "threshold"], "value": "10",
             "group": "Other layers speed"},
            # The speed row's unit is 'mm/s or %': a bare 50 is 50 mm/s. The
            # case wants 50% (pilot VALUES '50%'); run b1103170 stored '50'
            # and died at verification with the other five values right.
            {"op": "float", "label": "^Small perimeters", "value": "50%", "group": "Other layers speed"},
        ],
        "uia_param_fuzzy": [
            # atlas + band 244ae35e: the fuzzy rows are on the Others page
            # (Special mode area), NOT Quality - the case ran on the wrong
            # tab since authoring.
            # 2026-11-23 census 67690ed4 opened the popup: its rows are
            # None / Contour / Contour and hole / All walls - 'All external
            # walls' is the source label, not what this build paints. The
            # case wants external walls only = 'Contour' (fuzzy_skin
            # 'external'); 'All walls' stores 'allwalls' (run 1193a356).
            {"tab": "Others", "op": "rowcombo", "label": "Fuzzy skin",
             "target": "Contour", "group": "Fuzzy"},
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
        # 2026-11-23 (census c101c0f4): 'Detect overhang walls' is the first
        # row of the Quality page's LAST group, 'Overhangs' (y 2560 of a page
        # that starts at 730) - 55 rows below the top. Without its group the
        # scan never got there (run f775cd31).
        "uia_param_overhang_speeds": [
            {"tab": "Quality", "tab_hint": "height", "op": "checkbox", "label": "Detect overhang",
             "value": True, "group": "Overhangs"},
            {"tab": "Speed", "tab_hint": "speed", "op": "checkbox", "label": "Slow down",
             "value": True, "group": "Overhang"},
            {"op": "float", "label": "Overhang speed", "value": "40", "group": "Overhang", "field": 0},
            {"op": "float", "label": "Overhang speed", "value": "30", "group": "Overhang", "field": 1},
            {"op": "float", "label": "Overhang speed", "value": "20", "group": "Overhang", "field": 2},
            {"op": "float", "label": "Overhang speed", "value": "10", "group": "Overhang", "field": 3},
            # 2026-11-23 run 50798c59: the 2.4.0 project config has no
            # overhang_totally_speed key, so the fifth field is left alone
            # (the pilot records the deviation).
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
            # The Acceleration group paints 'First layer' (census: 'First
            # layer 500'), and its 'Travel' row is the 9th row - beyond the
            # first screen after the group title (run f149c3da).
            {"op": "float", "label": ["^First layer", "^Initial layer"], "value": "500",
             "group": "Acceleration"},
            {"op": "float", "label": "^Travel", "value": "8000",
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
            # 2026-11-23 census f1c5433b / 67690ed4: the popup's rows are
            # Mouse ear / Painted / Outer brim only / Inner brim only /
            # Outer and inner brim / No-brim - 'Outer only' never matched.
            {"tab": "Others", "op": "rowcombo", "label": "^Brim type", "target": "Outer brim only",
             "group": "Brim"},
            {"op": "float", "label": "^Brim width", "value": "5", "group": "Brim"},
            # The row paints 'Brim-object gap' (hyphen; screenshot f0e683fb).
            {"op": "float", "label": "gap", "value": "0.2", "group": "Brim"},
        ],
        # Feishu #276 (snapshot line 195): the table's filament/machine-scope
        # keys (filament_max_volumetric_speed, machine_max_speed_x) are not
        # reachable from the process panel and stay out of the ops/values.
        "uia_param_speed_limits": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["Layer height", "layer height"], "value": "0.2"},
            {"op": "float", "label": ["Outer wall line width", "^Outer wall"], "value": "0.42",
             "group": "Line width"},
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["Outer wall speed", "^Outer wall"], "value": "700",
             "group": "Other layers speed"},
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
        # 2026-11-24 queue22 (VM run 5a4728b6): every field landed, and the
        # app refused to slice - the slice button stays off with the toast
        # 'Jump to tree support': a raft is not made together with the TREE
        # support type, the fixture default. The Type combo is greyed until
        # support is on, so Enable then Type -> Normal go first (the #279
        # recipe); both keys are in the pilot as a recorded deviation.
        "uia_param_raft": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "float", "label": ["Raft layers", "Raft"],
             "value": "3", "group": "Raft"},
            {"op": "float", "label": ["Raft contact Z distance", "Raft contact distance",
                                      "Raft contact"], "value": "0.2", "group": "Raft"},
            # 2026-11-23: raft_expansion has NO row on the params page
            # (Tab.cpp appends only raft_layers/contact_distance/first_layer_
            # density/first_layer_expansion) - op and value dropped.
            # 2026-11-24 queue21 (VM run be0664ae): the first-layer rows are
            # NOT in the Raft group - the 2.4.0 page paints them as 'First
            # layer density' / 'First layer expansion' in the Support group,
            # above 'On build plate only' (row fixture param_ui_rows_2.4.0
            # .json). Raft holds 'Raft layers' and 'Raft contact Z distance'
            # only, and those two ops had already landed in that run.
            {"op": "float", "label": ["^First layer density", "First layer density"],
             "value": "100", "group": "Support"},
            {"op": "float", "label": ["^First layer expansion", "First layer expansion"],
             "value": "5", "group": "Support"},
        ],
        # Feishu #279 (line 198). 2026-11-23 census c814315c: the support
        # body filament is the 'Support/raft base' row (group 'Filament for
        # Supports'); it is greyed until support is enabled, so Enable goes
        # first. The extruder popup lists Default / 1 PETG / 2 PLA / ... -
        # 'PETG' names extruder 1 (the bare number is not OCR-stable). The
        # interface row already sits at 0 - no second op.
        "uia_param_support_filament": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            # 2026-11-23 queue20: with support on and the default Tree (auto)
            # type the app refuses to slice on this fixture ('Organic support
            # tree tip diameter must not be smaller than support material
            # extrusion width') - switch to Normal first, as #277 does.
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "rowcombo", "label": "^Support/raft base", "target": "PETG",
             "group": "Filament for Supports"},
        ],
        # Feishu #292 (line 211): clearance rows appear once by-object is set.
        "uia_param_by_object": [
            # 2026-11-23 screenshot f0e683fb: 'Print sequence' paints
            # 'By Layer'; 'Intra-layer order' is the NEXT row (an earlier
            # OCR band had glued the two rows together). The value is two
            # words, so the anchor is a word SEQUENCE.
            {"tab": "Others", "op": "combo", "current": ("By", "Layer"),
             "target": "By object", "group": "Special mode"},
            # 2026-11-23 atlas: the extruder-clearance rows live on the
            # PRINTER settings page (Basic information) - unreachable from
            # the process panel; ops dropped, keys dropped from VALUES
            # (precedent: raft_expansion).
        ],
        # Feishu #293 (line 212): spiral on Others, then the seam combo on
        # Quality (the m5h quality-enums route).
        # Feishu #293 (line 212): the Spiral vase tick makes the app ask
        # whether to switch wall loops / top layers / sparse infill to vase
        # values (ConfigManipulation.cpp:321-351) - the answer is Yes, and
        # those three keys are in the pilot's VALUES as a recorded
        # deviation (VM run 49723134: the box was never seen, see
        # param_case_lib.settle_dialog).
        "uia_param_spiral_vase": [
            {"tab": "Others", "op": "checkbox", "label": "Spiral",
             "value": True, "group": "Special mode", "answer": "Yes",
             "dialog": "Spiral mode"},
            {"tab": "Quality", "tab_hint": "height", "op": "combo", "current": "Aligned",
             "target": "nearest", "group": "Seam"},
        ],
        # Feishu #294 (line 213): slicing_mode already 'regular' in the
        # fixture config - only the timelapse selector is driven.
        "uia_param_timelapse": [
            {"tab": "Others", "op": "combo", "current": "None",
             "target": "Smooth", "group": "Special mode"},
        ],
        # Feishu #255 (line 174): rows paint SHORT feature names inside
        # the Quality 'Line width' group (PrintConfig labels: Default /
        # Initial layer / Outer wall / ... - Tab.cpp:2261), not the
        # table's *_line_width key names; 'Outer wall' also proven by the
        # #276 run pair.
        # 2026-11-24 (VM run e0905644): all seven fields landed and the
        # slicer refused - 'Too small line width' (Print.cpp
        # validate_extrusion_width: a width must be GREATER than the layer
        # height, and the fixture's layers are 0.4 mm; top surface 0.40 is
        # not above them). The table's values are written for thinner
        # layers: layer height 0.2 goes first, as a recorded deviation.
        "uia_param_line_width_all": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["^Layer height"], "value": "0.2", "group": "Layer height"},
            {"op": "float", "label": "Default",
             "value": "0.42", "group": "Line width"},
            # Band 513aabe1: the Quality top rows render "First layer ..."
            {"op": "float", "label": ["First layer", "Initial layer"], "value": "0.5", "group": "Line width"},
            {"op": "float", "label": ["Outer wall line width", "Outer wall"], "value": "0.42",
             "group": "Line width"},
            {"op": "float", "label": ["Inner wall line width", "Inner wall"], "value": "0.45",
             "group": "Line width"},
            {"op": "float", "label": "Top surface", "value": "0.4", "group": "Line width"},
            {"op": "float", "label": "Sparse infill", "value": "0.45", "group": "Line width"},
            {"op": "float", "label": ["Support line width", "Support"], "value": "0.42",
             "group": "Line width"},
        ],
        # Feishu #256 (line 175): seam_position/seam_gap/role_based_wipe_
        # speed already at target - no ops. Checkbox labels match ONE
        # OCR word (find_option_row is word-containment): 'Role' and
        # 'loops' are unique in the Seam band (band evidence: rows paint
        # 'Role base wipe speed' - sic, no d - and 'Wipe on loops').
        # Wipe speed may gray under role-based wipe, so uncheck -> type
        # -> recheck; final state matches the table.
        "uia_param_seam_wipe": [
            {"tab": "Quality", "tab_hint": "height", "op": "checkbox", "label": "Role",
             "value": False, "group": "Seam"},
            # '^': plain 'Wipe speed' resolved inside the previous row's
            # 'Role based wipe speed' (checkbox, run 13613ac7).
            {"op": "float", "label": "^Wipe speed", "value": "50", "group": "Seam"},
            {"op": "checkbox", "label": "Role", "value": True, "group": "Seam"},
            {"op": "checkbox", "label": "loops", "value": True, "group": "Seam"},
        ],
        # Feishu #257 (line 176): elefant_foot already 0.15 - no op. The
        # X-Y rows paint exactly 'X-Y hole/contour compensation' (band
        # result_28417). The 'Precise wall' checkbox is matched by the
        # word 'wall': every substring of 'Precise' also sits inside the
        # 'Precision' GROUP TITLE (word-containment would anchor the
        # title, which has no checkbox), and no word above the row
        # inside the group contains 'wall'.
        "uia_param_precision_comp": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["X-Y hole compensation", "hole compensation"], "value": "-0.1",
             "group": "Precision"},
            {"op": "float", "label": ["X-Y contour compensation", "contour compensation"],
             "value": "0.1", "group": "Precision"},
            {"op": "checkbox", "label": "wall", "value": True, "group": "Precision"},
        ],
        # Feishu #260 (line 179): five of seven targets already equal the
        # fixture values; the combo goes first because the Arachne
        # sub-rows stay inert while the generator reads Classic.
        "uia_param_wall_generator": [
            {"tab": "Quality", "tab_hint": "height", "op": "combo", "current": "Classic",
             "target": "Arachne", "group": "Wall generator"},
            {"op": "float", "label": ["Wall distribution count", "distribution count"],
             "value": "3", "group": "Wall generator"},
        ],
        # Feishu #261 (line 180): only_one_wall_top/min_width_top_surface
        # already at target - no ops. 'layer' anchors the first-layer
        # checkbox: no row with a checkbox above it paints 'layer'
        # ('Print infill first' / 'Wall loop direction' do not). The
        # detour Edit stays grayed until 'Avoid crossing walls' is on,
        # so that checkbox leads ('crossing' is band-unique).
        "uia_param_single_wall_avoid": [
            {"tab": "Quality", "tab_hint": "height", "op": "checkbox", "label": "layer",
             "value": True, "group": "Walls and surfaces"},
            {"op": "checkbox", "label": "crossing", "value": True,
             "group": "Walls and surfaces"},
            {"op": "float", "label": ["Max detour length", "detour length"], "value": "2",
             "group": "Walls and surfaces"},
        ],
        # Feishu #272 (line 191): the row label 'Overhang speed' equals
        # the group TITLE text, so a plain phrase anchors the title (no
        # Edit there -> clean raise). The value-anchored candidates pick
        # the field row itself - re-anchored per op to the values the
        # previous edit just painted (fixture paints 0 50 25 5).
        # overhang_totally_speed does not exist in this fork; bridge
        # speed and the enable flag already sit at the table targets.
        # 2026-11-23: rows anchored to the row label only. The value-bearing
        # phrases ('Overhang speed 0', ... 'Overhang speed 40 30 20') never
        # matched what OCR made of the painted field row (overhang_bridge run
        # ec02cd86: two 'not found' per op before the plain fallback); the
        # field index already selects the Edit.
        "uia_param_overhang_bridge": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": "Overhang speed", "value": "40",
             "group": "Overhang", "field": 0},
            {"op": "float", "label": "Overhang speed", "value": "30",
             "group": "Overhang", "field": 1},
            {"op": "float", "label": "Overhang speed", "value": "20",
             "group": "Overhang", "field": 2},
            {"op": "float", "label": "Overhang speed",
             "value": "10", "group": "Overhang", "field": 3},
        ],
        # Feishu #273 (line 192): the row paints just 'Travel' + the
        # value while the group TITLE reads 'Travel speed' - a plain
        # 'Travel' label anchors the title (no Edit -> raise), so lead
        # with the value-anchored phrase (fixture paints 500).
        "uia_param_travel_speed": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["Travel 500", "Travel speed", "Travel"], "value": "300",
             "group": "Travel speed"},
        ],
        # Feishu #258 (line 177): resolution / slice_closing_radius already
        # at target - no ops. The two Precision checkboxes anchor on single
        # band-unique words ('fitting' = Arc fitting; 'height' = Precise Z
        # height - the Layer height group above is scrolled out of band).
        "uia_param_arc_resolution": [
            {"tab": "Quality", "tab_hint": "height", "op": "checkbox",
             "label": "fitting", "value": True, "group": "Precision"},
            {"op": "checkbox", "label": "height", "value": True,
             "group": "Precision"},
        ],
        # Feishu #262 (line 181): print_flow_ratio already at target - no
        # op. Candidates stay prefixed to the painted rows so the group's
        # 'Only one wall on top surfaces' row ('top surfaces' tail) can
        # never prefix-match 'Top surface flow'.
        "uia_param_surface_flow": [
            {"tab": "Quality", "tab_hint": "height", "op": "float",
             "label": ["Top surface flow ratio", "Top surface flow"],
             "value": "1.1", "group": "Walls and surfaces"},
            {"op": "float", "label": ["Bottom surface flow ratio",
                                      "Bottom surface flow"], "value": "0.9",
             "group": "Walls and surfaces"},
        ],
        # Feishu #265 (line 184): the three fan keys are Filament-scope
        # (Cooling page, Tab.cpp:3847) - unreachable from the process panel
        # (#276 precedent). 'curled' is the band-unique word for the Slow
        # down for curled perimeters checkbox inside the Speed Overhang
        # speed group ('Slow down' alone would hit enable_overhang_speed).
        "uia_param_overhang_curl": [
            {"tab": "Speed", "tab_hint": "speed", "op": "checkbox",
             "label": "curled", "value": True, "group": "Overhang"},
        ],
        # Feishu #269 (line 188): internal_bridge_support_thickness is in
        # the loader ignore list (PrintConfig.cpp:7281) - not writable.
        # The combination checkbox precedes its max-layer sub-row, so the
        # first 'combination' word anchors the bool; the enum combo runs
        # LAST (a commit rebuilds the page) with the fork's slot-1 label
        # Critical Only (popup word 'Critical').
        "uia_param_infill_structure": [
            {"tab": "Strength", "tab_hint": "loops", "op": "checkbox",
             "label": "combination", "value": True, "group": "Advanced"},
            {"op": "float", "label": ["Minimum sparse infill threshold",
                                      "Minimum sparse infill"], "value": "10",
             "group": "Advanced"},
            {"op": "float", "label": ["External bridge infill direction",
                                      "External bridge infill",
                                      "External bridge"], "value": "45",
             "group": "Advanced"},
            {"op": "combo", "current": "All", "target": "Critical",
             "group": "Advanced"},
        ],
        # Feishu #275 (line 194): infill_jerk already at target - no op.
        # Jerk(XY) is second from the page bottom, so the speed and
        # acceleration rows sharing these short names sit ABOVE and scroll
        # out of band; value-anchored phrases lead (#272 recipe, fixture
        # paints 0/9/9/9/12), plain fallbacks resolve top-down (default_jerk
        # precedes 'Default junction deviation').
        "uia_param_jerk": [
            {"tab": "Speed", "tab_hint": "speed", "op": "float",
             "label": ["Default 0", "Default"], "value": "8", "group": "Jerk"},
            {"op": "float", "label": ["Outer wall 9", "Outer wall"],
             "value": "5", "group": "Jerk"},
            {"op": "float", "label": ["Inner wall 9", "Inner wall"],
             "value": "6", "group": "Jerk"},
            {"op": "float", "label": ["First layer 9", "First layer", "Initial layer 9", "Initial layer"],
             "value": "4", "group": "Jerk"},
            {"op": "float", "label": ["Travel 12", "Travel"], "value": "10",
             "group": "Jerk"},
        ],
        # Feishu #283 (line 202): five of eight keys already at target -
        # no ops. 'Prime' alone would anchor the group TITLE ('Prime
        # tower', no Edit); 'sparse' is the band-unique word for the No
        # sparse layers checkbox.
        "uia_param_prime_tower": [
            {"tab": "Multimaterial", "tab_hint": "tower", "op": "float",
             "label": ["Prime volume", "Prime vol"], "value": "40",
             "group": "Prime tower"},
            {"op": "checkbox", "label": "sparse", "value": True,
             "group": "Prime tower"},
            # 2026-11-24 queue21 (VM run aa451776): the apex-angle row exists
            # only while Wall type is Cone (ConfigManipulation.cpp:858
            # toggle_line("wipe_tower_cone_angle", ... wall_type == wtwCone))
            # - with the goal's rib walls the page goes Wall type / Extra
            # rib length / Rib width / Fillet wall and the scan ran to the
            # page end. The goal wants rib walls AND angle 15: switch to
            # Cone, set the angle, switch back to Rib. The value stays in
            # the config while the row is hidden (the proof reads the saved
            # project, both keys are in VALUES).
            {"op": "rowcombo", "label": "^Wall type", "target": "Cone",
             "group": "Prime tower"},
            {"op": "float", "label": ["Stabilization cone apex angle",
                                      "Stabilization cone"], "value": "15",
             "group": "Prime tower"},
            {"op": "rowcombo", "label": "^Wall type", "target": "Rib",
             "group": "Prime tower"},
        ],
        # Feishu #285 (line 204): ooze_prevention already at target - no
        # op. 'variation' anchors Temperature variation; the two Preheat
        # rows sit adjacent, so the phrase join ('Preheat time' vs
        # 'Preheat steps') tells them apart.
        "uia_param_ooze_prevention": [
            {"tab": "Multimaterial", "tab_hint": "tower", "op": "float",
             "label": ["Temperature variation", "variation"], "value": "-100",
             "group": "Ooze prevention"},
            {"op": "float", "label": ["Preheat time", "Preheat"], "value": "15",
             "group": "Ooze prevention"},
            # 2026-11-23 run fb7cb075: the 2.4.0 Ooze prevention group is
            # Enable / Temperature variation / Preheat time / Preheat delta
            # temperature - there is no 'Preheat steps' row. The pilot
            # records the deviation.
        ],
        # Feishu #280 (line 199): flow already '10%' and pattern already
        # 'rectilinear' - no ops. The ironing checkbox row paints 'lroning
        # Support lnterface' (OCR leading-I quirk): 'roning' containment
        # hits the group's FIRST row = the checkbox; the spacing Edit
        # anchors on the OCR-safe 'line spacing' tail.
        "uia_param_support_ironing": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            # 2026-11-23 queue20: with support on and the default Tree (auto)
            # type the app refuses to slice on this fixture ('Organic support
            # tree tip diameter must not be smaller than support material
            # extrusion width') - switch to Normal first, as #277 does.
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "checkbox", "label": "roning", "value": True,
             "group": "Support ironing"},
            # 2026-11-23 run 001573f1: the row paints 'Support Ironing
            # linespacing' (one word).
            {"op": "float", "label": ["Support Ironing linespacing", "linespacing",
                                      "line spacing", "Ironing line spacing",
                                      "lroning line spacing"], "value": "0.15",
             "group": "Support ironing"},
        ],
        # Feishu #281 (line 200): top/bottom Z distance already 0.2 - no
        # ops. 'Top lnterface ...' candidates lead with the OCR-quirk
        # spelling (leading-I quirk); the pattern combo runs LAST (page
        # rebuild) and its 'Auto' value is band-unique with the Advanced
        # group pre-scrolled (the Support group's 'Tree (auto)' sits out
        # of band; popup's first 'Rectilinear' word = the plain pattern).
        "uia_param_support_interface": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            # 2026-11-23 queue20: with support on and the default Tree (auto)
            # type the app refuses to slice on this fixture ('Organic support
            # tree tip diameter must not be smaller than support material
            # extrusion width') - switch to Normal first, as #277 does.
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "float", "label": ["Support/object xy distance",
                                      "xy distance"], "value": "0.5",
             "group": "Advanced"},
            {"op": "float", "label": ["Top lnterface layers",
                                      "Top interface layers"], "value": "3",
             "group": "Advanced"},
            {"op": "float", "label": ["Top lnterface spacing",
                                      "Top interface spacing"], "value": "0",
             "group": "Advanced"},
            # 2026-11-23 census c814315c: the Advanced group's combo row is
            # 'Interface pattern' (popup: Rectilinear / Concentric /
            # Rectilinear Interlaced / Grid); no value 'Auto' is painted.
            {"op": "rowcombo", "label": "Interface pattern", "target": "Rectilinear",
             "group": "Advanced"},
        ],
        # Feishu #282 (line 201): support_type already 'tree(auto)',
        # branch_diameter already 2, adaptive_layer_height already 1 - no
        # ops. The fork defaults support_style to organic (ConfigManipulation
        # :691-703) which HIDES branch_angle/adaptive/max_bridge, so the
        # Style combo ('Default' -> 'Tree Slim', popup word 'Slim') must run
        # before the floats; each later op re-anchors by its own group.
        # wall loops + max bridge live in 'Advanced'. The branch angle is in
        # the 'Tree supports' group, which is CONDITIONAL: census c101c0f4
        # saw no such title on the default page, and queue21 (VM run
        # 1f23038c) showed why - the title and its rows (Tree support
        # branch distance / diameter / angle, Adaptive layer height) appear
        # only after Style leaves 'Default'. The scan confined to 'Advanced'
        # OCR'd 'Tree support branch angle' in the very next band and still
        # reported param_row; the group is 'Tree supports' now.
        "uia_param_tree_support": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            {"op": "combo", "current": "Default", "target": "Slim",
             "group": "Support"},
            {"op": "float", "label": ["Tree support branch angle",
                                      "branch angle"], "value": "40",
             "group": "Tree supports"},
            {"op": "float", "label": ["Support wall loops", "wall loops"],
             "value": "1", "group": "Advanced"},
            {"op": "float", "label": ["Max bridge length", "bridge length"],
             "value": "30", "group": "Advanced"},
        ],
        # Feishu #284 (line 203): wipe_tower_filament (Multimaterial
        # 'Filament for Features') and support_interface_filament already
        # 0 - assertion-only; the single op is the proven #279 support
        # body rowcombo.
        # 2026-11-23 atlas: wipe_tower_filament is the 'Wipe tower' row of
        # MULTIMATERIAL / 'Filament for Features'. On the Support tab the
        # word 'filament' only hit the group TITLE 'Filament for Supports'
        # (no combo there - run be75f8b8: param_combo_popup).
        # 2026-11-23 census 40989dec / c814315c: that Multimaterial group is
        # Walls / Infill / Solid infill / Wipe tower - no support row. The
        # support body filament is the Support tab's 'Support/raft base'
        # (#279), greyed until support is on. Same ops as #279.
        "uia_param_filament_features": [
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            # 2026-11-23 queue20: with support on and the default Tree (auto)
            # type the app refuses to slice on this fixture ('Organic support
            # tree tip diameter must not be smaller than support material
            # extrusion width') - switch to Normal first, as #277 does.
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "rowcombo", "label": "^Support/raft base", "target": "PETG",
             "group": "Filament for Supports"},
        ],
        # Feishu #286 (line 205): flush_into_support already 1 - no op.
        # 'objects' containment hits the infill row (group's first row,
        # apostrophe-proof); the group title's 'Flush' is never an anchor
        # (titles carry no checkbox).
        # 2026-11-24 queue21 (VM run): the 'this' op is gone - the middle
        # row 'Flush into this object' is not painted in the GLOBAL config
        # (ConfigManipulation.cpp:886 toggle_line("flush_into_objects",
        # !is_global_config)); the page shows infill + support only (row
        # fixture) and the run died on param_checkbox:this. flush_into_objects
        # leaves the pilot's VALUES with a recorded deviation.
        "uia_param_flush_options": [
            {"tab": "Multimaterial", "tab_hint": "tower", "op": "checkbox",
             "label": "objects", "value": True, "group": "Flush options"},
            {"op": "float", "label": ["Prime volume", "Prime vol"],
             "value": "40", "group": "Prime tower"},
        ],
        # Feishu #287 (line 206): support_interface_filament already 0 and
        # interface_shells is coBool - the table's '=2' writes as 1
        # (module header records the deviation). 'shells' is band-unique
        # and OCR-safe; then the #279 ops on Support (census c814315c).
        "uia_param_material_advanced": [
            {"tab": "Multimaterial", "tab_hint": "tower", "op": "checkbox",
             "label": "shells", "value": True, "group": "Advanced"},
            {"tab": "Support", "tab_hint": "support", "op": "checkbox",
             "label": "Enable", "value": True, "group": "Support"},
            # 2026-11-23 queue20: with support on and the default Tree (auto)
            # type the app refuses to slice on this fixture ('Organic support
            # tree tip diameter must not be smaller than support material
            # extrusion width') - switch to Normal first, as #277 does.
            {"op": "combo", "current": "Tree", "target": "Normal", "group": "Support"},
            {"op": "rowcombo", "label": "^Support/raft base", "target": "PETG",
             "group": "Filament for Supports"},
        ],
        # Feishu #296 (line 215): gcode_label_objects already 1 - no op.
        # Others carries NO tab_hint (param_tab:Others lesson). 'Verbose'
        # and 'number' are band-unique checkbox words; the filename Edit
        # is the family's one text field - VALUES is the real gate (the
        # digit-only readback cannot verify braces).
        "uia_param_gcode_output": [
            {"tab": "Others", "op": "checkbox", "label": "Verbose",
             "value": True, "group": "G-code output"},
            {"op": "checkbox", "label": "number", "value": True,
             "group": "G-code output"},
            {"op": "float", "label": ["Filename format", "format"],
             "value": "{input_filename_base}_{plate_name}.gcode",
             "group": "G-code output"},
        ],
        # Feishu #297 (line 216): reduce_infill_retraction already 1 - no
        # op. 'Exclude' is band-unique on the Others page.
        "uia_param_exclude_objects": [
            {"tab": "Others", "op": "checkbox", "label": "Exclude",
             "value": True, "group": "G-code output"},
        ],
        # Save-only controls (2026-11-24): no operation. run_ops still switches
        # Advanced on, then the worker saves, reopens, slices and exports as for
        # every parameter case. The cube here; the precondition fixture in the
        # second (native_pilots.native_fixture).
        "uia_param_save_only": [],
        STD_SCENARIO: [],
}


def scenario_ops(scenario):
    """The ops `scenario` runs: its base scenario's PARAM_OPS entry (None when it has
    none). A `_std02` scenario is that scenario on the precondition fixture, whose
    filaments are all PLA: its extruder popup rows are "1 PLA" .. "5 PLA" (the rows
    paint "<n> <filament type>", census 67690ed4 / c814315c), so a rowcombo target that
    named the cube's extruder 1 by its type names row 1 there
    (agent_protocol.STD_TARGETS). The table is not touched - it stays what the cube
    runs; only an op whose target was substituted comes back as a copy."""
    base = base_scenario(scenario)
    ops = PARAM_OPS.get(base)
    substituted = lambda op: op.get("op") == "rowcombo" and op.get("target") in STD_TARGETS
    if ops is None or base == scenario or not any(substituted(op) for op in ops):
        return ops
    return [dict(op, target=STD_TARGETS[op["target"]]) if substituted(op) else op for op in ops]


def _save_failure_shot(ui, scenario):
    """Screenshot of the sidebar at the moment a param case failed. The OCR
    band text in the log is ambiguous (run f0e683fb: 'Print sequence
    Intra-layer order' read as one value was two rows), the picture is not.
    Saved under the run's artifacts root and picked up by hv_harvest."""
    try:
        from PIL import Image
        from . import process_panel as pp
        Image.fromarray(pp.capture_bgr(ui.app)[:, :, ::-1]).save(ui.artifacts / "param_failure.png")
        print("[param] failure screenshot: %s" % (ui.artifacts / "param_failure.png"), flush=True)
    except Exception as exc:
        print("[param] failure screenshot failed: %s" % type(exc).__name__, flush=True)


def edit_param_cases(ui, scenario):
    """Feishu 常用工艺参数 supplement cases (declarative process-panel ops)."""
    from .param_case_lib import run_ops

    ops = scenario_ops(scenario)
    if ops is None:
        raise ProtocolError("param_case_ops:" + scenario)
    try:
        run_ops(ui, ops)
    except Exception:
        import traceback
        traceback.print_exc()
        _save_failure_shot(ui, scenario)
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
    # A `_std02` name is dispatched as its base scenario: only the fixture differs.
    base = base_scenario(scenario)
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
    elif base == "uia_param_layer_pair":
        edit_param_layer_pair(ui)
    elif base in ("uia_param_census", "uia_param_census_develop"):
        from .param_case_lib import census_param_pages
        census_param_pages(ui)
    elif base == "uia_param_mix_census":
        from .param_mix_census import census_mix_dialog
        census_mix_dialog(ui)
    elif scenario.startswith("uia_param_"):
        edit_param_cases(ui, scenario)
    else:
        raise ProtocolError("script_comparison_scenario")
