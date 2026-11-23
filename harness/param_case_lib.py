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
            # 2026-11-22 run 992adb68: the app serializes an EDITED value as a
            # one-element list ('60' -> ['60'], ironing_speed) while untouched
            # keys keep scalar form - accept both shapes.
            if isinstance(got, list) and len(got) == 1 and not isinstance(want, list):
                got = got[0]
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
                # 2026-11-23 run 4380d8ff: analyze_gcode reports the count
                # under 'ironing_xy_e_moves' (agent_layer_verify.py:193);
                # the old key 'ironing_moves' never existed, so every
                # ironing case failed the schedule check with 0.
                _require(layers.get("ironing_xy_e_moves", 0) >= ironing["min_moves"],
                         "param_ironing_moves")
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


def _find_phrase_row(app, phrase, group_substr=None):
    """Row y of a painted label that may span several OCR words.

    pp.find_option_row only matches a substring inside ONE word (why
    'density' works and 'Wall loops' never did); join adjacent words and
    match the phrase, falling back to single-word containment."""
    from . import process_panel as pp
    import time

    if group_substr:
        pp.scroll_group_into_view(app, group_substr)
    want = phrase.lower().split()
    # 2026-11-22: 6 single-notch wheels never reach deep groups; the fa706g3
    # pathology forbids multi-notch steps (they reset to top).
    # 2026-11-23: an edit commit REBUILDS the panel and the scroll can land
    # anywhere (run 983bab81: search started at the page bottom after an
    # edit) - scan down first, then back up past the start position.
    for direction in (-120, 120):
        for _ in range(12 if direction == -120 else 26):
            words = pp.ocr_band(app, psm=3)
            for i, (w, x, y, ww, hh) in enumerate(words):
                if len(want) == 1 and want[0] in w.lower():
                    return y + hh // 2
                if len(want) > 1 and w.lower().startswith(want[0]):
                    tail = " ".join(t for t, *_ in words[i:i + len(want)]).lower()
                    if tail.startswith(phrase.lower()):
                        return y + hh // 2
            vp = pp.options_viewport(app)
            if vp:
                pp.wheel_viewport(app, vp, 1, delta=direction)
            time.sleep(0.4)
    print("[param-phrase] not found: " + phrase + " | last band: " +
          " ".join(w for w, *_ in words)[:160], flush=True)
    return None


def uia_set_float(ui, label_substr, value, group_substr=None, field_index=0):
    """Set a sidebar float Edit: OCR locates the painted row (OG_CustomCtrl
    draws row labels without HWNDs - only group headers are windows, the
    f5acdb1a census), then the visible Edit whose row-y matches is driven
    through the proven ui.edit commit. No x-column calibration (the m4g
    band does not hold on every page - runs 47bccc5a+)."""
    from win32gui import EnumChildWindows, IsWindowVisible, IsWindowEnabled

    wu, app = ui.wu, ui.app
    y_row = _find_phrase_row(app, label_substr, group_substr)
    if y_row is None:
        raise ProtocolError("param_row:" + label_substr)
    left, top, right, bottom = wu.window_rect(_canvas_hwnd(ui))
    origin_x, origin_y = wu.client_to_screen(app.hwnd, 0, 0)
    matches = []

    def collect(handle, _):
        if (wu.window_class(handle) != "Edit" or not IsWindowVisible(handle)
                or not IsWindowEnabled(handle) or wu._window_pid(handle) != app.pid):
            return True
        b = wu.window_rect(handle)
        cy = (b[1] + b[3]) // 2 - origin_y
        # the parameter sidebar sits LEFT of the canvas (calibration run
        # 6bc47e55: row_y 762 vs Edit cy 764 at x 267, canvas_left 426).
        if abs(cy - y_row) <= 14 and 0 <= (b[0] + b[2]) // 2 < left:
            matches.append((handle, list(b)))
        return True

    EnumChildWindows(app.hwnd, collect, None)
    # 2026-11-22 #264: the five overhang degree-band speeds render as ONE
    # labelled row with five inline Edits (Tab.cpp: Line{L("Overhang speed")}
    # ...append_option x5); select left-to-right by field_index instead of
    # failing on the multi-match.
    matches.sort(key=lambda m: m[1][0])
    if len(matches) > 1 and 0 <= field_index < len(matches):
        print(f"[param-uia] row '{label_substr}' has {len(matches)} edits; "
              f"driving field[{field_index}]", flush=True)
        handle, bounds = matches[field_index]
    elif len(matches) == 1:
        handle, bounds = matches[0]
    else:
        from win32gui import EnumChildWindows as _ecw2
        seen = []

        def survey(handle, _):
            if (wu.window_class(handle) != "Edit" or not IsWindowVisible(handle)
                    or wu._window_pid(handle) != app.pid):
                return True
            b = wu.window_rect(handle)
            seen.append(f"@{handle} cy={(b[1]+b[3])//2-origin_y} sx={b[0]}; ")
            return True

        _ecw2(app.hwnd, survey, None)
        print(f"[param-uia] row_y={y_row} canvas_left={left} edits=" + "".join(seen)[:600], flush=True)
        raise ProtocolError("param_uia_field:" + label_substr + ":" + str(len(matches)))
    x = (bounds[0] + bounds[2]) // 2 - origin_x
    y = (bounds[1] + bounds[3]) // 2 - origin_y
    receipt = ui.edit(x, y, str(value))
    from decimal import Decimal as _D, InvalidOperation as _Inv

    def _num(text):
        digits = "".join(ch for ch in str(text) if ch.isdigit() or ch == ".")
        try:
            return _D(digits)
        except _Inv:
            return None

    if (receipt["target_hwnd"] != handle
            or _num(receipt["after_text"]) != _num(value)):
        raise ProtocolError("param_uia_readback:" + label_substr + ":" + repr(receipt.get("after_text"))[:40])


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
            labels = op["label"] if isinstance(op["label"], (tuple, list)) else (op["label"],)
            last = None
            for candidate in labels:
                try:
                    uia_set_float(ui, candidate, str(op["value"]), group_substr=op.get("group"),
                                  field_index=op.get("field", 0))
                    last = None
                    break
                except ProtocolError as exc:
                    last = exc
            if last is not None:
                raise last
            pp.neutralize_focus(app)
        elif kind == "checkbox":
            ok = pp.set_option_checkbox(app, op["label"], op["value"], group_substr=op.get("group"))
            # set_option_checkbox returns (now_on, rect); for want=False a
            # SUCCESSFUL uncheck returns ok[0]=False - the old `is True` check
            # rejected every unchecked-success (seam_wipe 'Role' att0 did
            # 0.21->0.06 then raised, run 7cb0e911).
            if not (isinstance(ok, tuple) and ok[0] == op["value"]):
                raise ProtocolError("param_checkbox:" + op["label"])
            # 2026-11-23: enabling some options (Spiral vase, run c6584b3e)
            # pops an informational modal that trips the next guard
            # (main_window_modal_blocked) - close any popup that appears.
            from . import export_util as _eu
            _modal = _eu.wait_popup(app.pid, timeout_s=1.2)
            if _modal:
                from . import winutil as _wl
                _wl.user32.PostMessageW(_modal[3], 0x0010, 0, 0)  # WM_CLOSE
                ui.pause(0.6)
        elif kind == "rowcombo":
            from .param_combo_row import pick_combo_at_label
            pick_combo_at_label(ui, op["label"], op["target"], group_substr=op.get("group"))
        elif kind == "combo":
            # set_combo_by_popup returns (ok, target_confirmed); the bare
            # tuple was always truthy, silently passing locate failures
            # through (#259 run 9b9048c4: 'No ironing' never found, the op
            # still "succeeded" and the case died later at the Speed row).
            ok, _confirmed = pp.set_combo_by_popup(app, op["current"], op["target"],
                                                    group_substr=op.get("group"),
                                                    log="[param case]")
            if not ok:
                raise ProtocolError("param_combo:" + op["target"])
        else:
            raise ProtocolError("param_op:" + str(kind))
        ui.pause(1.0)
    ui.pause(6)
    ui.main_input()
