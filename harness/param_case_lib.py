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

    EnumChildWindows(app.hwnd, collect)
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

    EnumChildWindows(app.hwnd, collect)
    if len(hits) != 1:
        raise ProtocolError("param_canvas_anchor:" + str(len(hits)))
    return hits[0]


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
    """Set a sidebar float Edit via UIA ValuePattern + native Enter.

    The painted label left of the field identifies it (the same pairing
    the zcode observations expose); the m4g x-column calibration does not
    hold on every page, but UIA reaches the Edit regardless of layout."""
    import sys
    sys.path.insert(0, r"C:\coil\tools\windows-mcp-0.8.9\Lib\site-packages")
    from windows_mcp.uia import ControlFromHandle

    app = ui.app
    root = ControlFromHandle(app.hwnd)
    labels = _sidebar_label_rows(ui)
    wanted = label_substr.strip().casefold()
    pending = [(root, 0)]
    matches = []
    while pending:
        element, depth = pending.pop()
        if depth < 12:
            pending.extend((child, depth + 1) for child in element.GetChildren())
        if element.ControlTypeName != "EditControl" or not element.NativeWindowHandle:
            continue
        if not element.IsEnabled or element.IsOffscreen:
            continue
        rect = element.BoundingRectangle
        field = [rect.left, rect.top, rect.right, rect.bottom]
        label = _row_label_at(labels, field)
        if label and wanted in label.casefold():
            matches.append((element, label))
    if len(matches) != 1:
        raise ProtocolError("param_uia_field:" + label_substr + ":" + str(len(matches)))
    element, _ = matches[0]
    pattern = element.GetValuePattern()
    if not pattern.SetValue(str(value)) or element.GetValuePattern().Value != str(value):
        raise ProtocolError("param_uia_write:" + label_substr)
    from win32gui import IsWindow
    handle = element.NativeWindowHandle
    if IsWindow(handle):
        ui.wu.msg_text(handle, "\r")  # the proven native-Enter commit
    if element.GetValuePattern().Value != str(value):
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
