"""Shared machinery for the Feishu 常用工艺参数 supplement cases.

Each case = a values dict (config keys the case may change, with target
values) plus G-code expectations the existing analyzers can prove. This
library builds verify_business implementations from such specs and keeps
the change-scope registry the settings-preservation check admits."""
from decimal import Decimal

from .agent_layer_verify import analyze_gcode
from .agent_protocol import ProtocolError
from .agent_verify import _require
from .pilot_common import _register_param_change_scope, inspect_preserved_settings
from .project_3mf import _archive, _json


def make_verify(case_id, values, *, schedule=None, ironing=None, cancelled_guard=True):
    """Build verify_business(project, fixture, gcode) for a parameter case.

    schedule: dict(layer_count=..., last_z=...) when the case leaves object
    geometry unchanged (the standard cube keeps 68 x 0.4 / 27.2).
    ironing: dict(speed_comment=..., min_moves=...) to require ironing
    moves and the configured speed via analyze_gcode's ironing inspection.
    """
    _register_param_change_scope(values)

    def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
        actual, original = (_json(a["Metadata/project_settings.config"])
                            for a in (_archive(project, cancelled), _archive(fixture, cancelled)))
        inspect_preserved_settings(actual, original, allowed_changes=values, cancelled=cancelled)
        result = {"case_id": case_id, "other_settings_preserved": True}
        for key, want in values.items():
            got = actual.get(key)
            _require(Decimal(str(got)) == Decimal(str(want)) if _numeric(want) else got == want,
                     "param_value:" + key)
            result[key] = got
        if schedule or ironing:
            layers = analyze_gcode(gcode, layer_height=str(actual.get("layer_height", "0.4")),
                                   first_layer_height=str(actual.get("initial_layer_print_height", "0.4")),
                                   inspect_ironing=bool(ironing), cancelled=cancelled)
            if schedule:
                _require(layers["layer_count"] == schedule["layer_count"], "param_layer_count")
                _require(Decimal(layers["last_z"]) == Decimal(schedule["last_z"]), "param_last_z")
            if ironing:
                _require(layers.get("ironing_moves", 0) >= ironing["min_moves"], "param_ironing_moves")
            result["layer_count"] = layers["layer_count"]
            result["last_z"] = layers["last_z"]
            result["gcode_sha256"] = layers["sha256"]
        return result

    return verify_business


def _numeric(value):
    try:
        Decimal(str(value))
        return True
    except Exception:
        return False


# ---- baseline-side: declarative process-panel operations -------------------

def _sidebar_label_rows(ui):
    """[(title, bounds)] of drawn wx label windows left of the canvas."""
    from win32gui import EnumChildWindows, IsWindowVisible

    wu, app = ui.wu, ui.app
    from .native_uia_hybrid import within
    left, top, right, bottom = wu.window_rect(_canvas_hwnd(ui))
    sidebar = [0, top, left, bottom]
    found, ambiguous = {}, set()

    def collect(handle, _):
        if (wu.window_class(handle) != "wxWindowNR" or not IsWindowVisible(handle)
                or wu._window_pid(handle) != app.pid):
            return True
        title = wu.window_title(handle).strip()
        bounds = list(wu.window_rect(handle))
        if (not title or title == "panel" or len(title) < 3
                or bounds[2] - bounds[0] > 400 or not within(sidebar, bounds)):
            return True
        if title in found:
            ambiguous.add(title)
        else:
            found[title] = bounds
        return True

    EnumChildWindows(app.hwnd, collect, None)
    return [(t, found[t]) for t in found if t not in ambiguous]


def _canvas_hwnd(ui):
    """The wxGLCanvas child anchor (same source as the hybrid guard)."""
    from win32gui import EnumChildWindows

    wu, app = ui.wu, ui.app
    hits = []

    def collect(handle, _):
        if wu.window_class(handle) == "wxGLCanvas" and wu._window_pid(handle) == app.pid:
            hits.append(handle)
        return True

    EnumChildWindows(app.hwnd, collect, None)
    if not hits:
        raise ProtocolError("param_canvas_anchor:0")
    # The 3D viewport dwarfs thumbnail/preview GL canvases (measured: 3
    # wxGLCanvas children on this build) - anchor the sidebar on the largest.
    return max(hits, key=lambda h: (lambda r: (r[2] - r[0]) * (r[3] - r[1]))(wu.window_rect(h)))


def _row_label_at(labels, field):
    best_title, best_gap = None, 10**6
    center_field = (field[1] + field[3]) / 2
    for title, bounds in labels:
        if bounds[2] > field[0] or bounds[3] < field[1] or bounds[1] > field[3]:
            continue
        center_label = (bounds[1] + bounds[3]) / 2
        if abs(center_label - center_field) > 14:
            continue
        gap = field[0] - bounds[2]
        if 0 <= gap < best_gap:
            best_title, best_gap = title, gap
    return best_title if best_title is not None and best_gap <= 300 else None


def uia_set_float(ui, label_substr, value):
    """Set a sidebar float Edit by label pairing + the proven ui.edit commit.

    Pure Win32: enumerate visible Edit children, pair each with its painted
    row label (no x-column calibration - runs 47bccc5a+ proved the m4g band
    does not hold on every page), then drive ui.edit (msg-level typing with
    readback), the same mechanism edit_layer has used GREEN since the
    script baselines landed."""
    from win32gui import EnumChildWindows, IsWindowVisible, IsWindowEnabled

    wu, app = ui.wu, ui.app
    labels = _sidebar_label_rows(ui)
    wanted = label_substr.strip().casefold()
    matches = []

    def collect(handle, _):
        if (wu.window_class(handle) != "Edit" or not IsWindowVisible(handle)
                or not IsWindowEnabled(handle) or wu._window_pid(handle) != app.pid):
            return True
        bounds = list(wu.window_rect(handle))
        label = _row_label_at(labels, bounds)
        if label and wanted in label.casefold():
            matches.append((handle, label, bounds))
        return True

    EnumChildWindows(app.hwnd, collect, None)
    if len(matches) != 1:
        dump = []

        def survey(handle, _):
            if (wu.window_class(handle) != "Edit" or not IsWindowVisible(handle)
                    or not IsWindowEnabled(handle) or wu._window_pid(handle) != app.pid):
                return True
            b = list(wu.window_rect(handle))
            dump.append(f"Edit@{handle} {b} label={_row_label_at(labels, b)!r}; ")
            return True

        EnumChildWindows(app.hwnd, survey, None)
        print("[param-uia] labels=" + repr([t for t, _ in labels])[:400], flush=True)
        print("[param-uia] edits=" + ("".join(dump)[:900] or "NONE"), flush=True)
        raise ProtocolError("param_uia_field:" + label_substr + ":" + str(len(matches)))
    handle, _label, bounds = matches[0]
    origin_x, origin_y = wu.client_to_screen(app.hwnd, 0, 0)
    x = (bounds[0] + bounds[2]) // 2 - origin_x
    y = (bounds[1] + bounds[3]) // 2 - origin_y
    receipt = ui.edit(x, y, str(value))
    from decimal import Decimal as _D
    if (receipt["target_hwnd"] != handle
            or _D(str(receipt["after_text"])) != _D(str(value))):
        raise ProtocolError("param_uia_readback:" + label_substr)


def run_ops(ui, ops):
    """Execute a list of process-panel operations on the running app.

    op forms:
      {"tab": "Quality", ...} switches the parameter tab first;
      {"op": "float",   "label": ..., "value": ...}  (UIA, label-paired)
      {"op": "checkbox","label": ..., "value": True, ["group": ...]}
      {"op": "combo",   "current": ..., "target": ..., ["group": ...]}
    """
    from . import process_panel as pp

    app = ui.app
    ui.main_input()
    # Without Advanced the parameter pages show summary rows only - no
    # individual float Edits (m5c precedent; runs d536b165/4fb3929a).
    pp.ensure_advanced(app, want=True)
    current_tab = None
    for op in ops:
        tab = op.get("tab") or current_tab
        if tab and tab != current_tab:
            ui.main_input()
            if not pp.click_tab(app, tab, op.get("tab_hint", "")):
                raise ProtocolError("param_tab:" + tab)
            current_tab = tab
            ui.pause(1.0)
        ui.main_input()
        kind = op["op"]
        if kind == "float":
            uia_set_float(ui, op["label"], str(op["value"]))
            pp.neutralize_focus(app)
        elif kind == "checkbox":
            ok = pp.set_option_checkbox(app, op["label"], op["value"], group_substr=op.get("group"))
            if ok is not True and not (isinstance(ok, tuple) and ok[0] is True):
                raise ProtocolError("param_checkbox:" + op["label"])
        elif kind == "combo":
            ok = pp.set_combo_by_popup(app, op["current"], op["target"],
                                       group_substr=op.get("group"),
                                       log="[param case]")
            if not ok:
                raise ProtocolError("param_combo:" + op["target"])
        else:
            raise ProtocolError("param_op:" + str(kind))
        ui.pause(1.0)
    ui.pause(6)
    ui.main_input()
