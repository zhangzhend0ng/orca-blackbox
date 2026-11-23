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
    match the phrase, falling back to single-word containment.

    A leading '^' anchors the phrase to the START of its row: 'Wipe speed'
    otherwise resolves inside the previous row's 'Role based wipe speed' (a
    checkbox row - run 13613ac7) and 'Travel' inside 'Initial layer travel'
    (run f149c3da). With `group_substr` a hit outside that group's band is
    skipped, so 'Outer wall' of the Acceleration group cannot resolve to the
    same label of the speed or jerk group (run f0e683fb screenshot). The scan
    is down first, then back up past the start position (an edit commit
    rebuilds the panel and the scroll lands anywhere, run 983bab81), and it
    resets the keyboard focus whenever the wheel stops moving the panel."""
    from . import process_panel as pp
    import time

    if group_substr:
        pp.scroll_group_into_view(app, group_substr)
    anchored = phrase.startswith("^")
    phrase = phrase[1:] if anchored else phrase
    want = phrase.lower().split()

    def hit(i, words):
        w, x, y, ww, hh = words[i]
        if anchored and not pp.leftmost_on_line(words, i):
            return False
        # A group title is spelled like some of its rows ('Layer height',
        # 'First layer speed'): it is not a row (speed_limits run fc5b643c).
        if pp.on_title_line(app, y):
            return False
        if len(want) == 1:
            return want[0] in w.lower()
        if not w.lower().startswith(want[0]):
            return False
        tail = " ".join(t for t, *_ in words[i:i + len(want)]).lower()
        return tail.startswith(phrase.lower())

    stall = pp._StallGuard(app, "phrase %r%s" % (phrase, " in %r" % group_substr if group_substr else ""))
    found = None
    words = []
    for direction in (-120, 120):
        stall.reset()
        started = time.monotonic()
        for _ in range(pp.SCAN_NOTCHES):
            if time.monotonic() - started > pp.SCAN_SECONDS:
                print("[param-phrase] %ss cap reached scanning %s for %r" % (
                    pp.SCAN_SECONDS, "down" if direction < 0 else "up", phrase), flush=True)
                break
            # Re-read every step: the span is in client coordinates and the
            # page moves under it. Frozen at the start it rejected the
            # group's own rows once they had scrolled above the title's
            # starting position (queue18).
            span = pp.group_span(app, group_substr) if group_substr else None
            words = pp.ocr_band(app, psm=3)
            for i in range(len(words)):
                if hit(i, words) and (span is None or span[0] <= words[i][2] < span[1]):
                    found = words[i][2] + words[i][4] // 2
                    break
            if found is not None:
                break
            vp = pp.options_viewport(app)
            if vp:
                if stall.step(words):
                    break
                pp.wheel_viewport(app, vp, 1, delta=direction)
            time.sleep(0.4)
        if found is not None:
            break
    if found is None:
        print("[param-phrase] not found: " + phrase + " | last band: " +
              " ".join(w for w, *_ in words)[:160], flush=True)
    return found


def uia_set_float(ui, label_substr, value, group_substr=None, field_index=None, below=False):
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
    greyed = []   # Edits on the label's own line that are disabled

    def collect(handle, _):
        if (wu.window_class(handle) != "Edit" or not IsWindowVisible(handle)
                or wu._window_pid(handle) != app.pid):
            return True
        b = wu.window_rect(handle)
        cy = (b[1] + b[3]) // 2 - origin_y
        # the parameter sidebar sits LEFT of the canvas (calibration run
        # 6bc47e55: row_y 762 vs Edit cy 764 at x 267, canvas_left 426).
        if y_lo <= cy <= y_hi and 0 <= (b[0] + b[2]) // 2 < left:
            if IsWindowEnabled(handle):
                matches.append((handle, list(b)))
            else:
                greyed.append(handle)
        return True

    y_lo, y_hi = y_row - 14, y_row + 14
    EnumChildWindows(app.hwnd, collect, None)
    if greyed and not (field_index is not None or below):
        # A greyed field means the row is disabled by another setting
        # (Brim width under Brim type = Auto). Say so instead of reporting
        # a bare "0 edits" that reads like a lookup miss.
        print(f"[param-uia] row '{label_substr}' y={y_row}: field is disabled "
              f"(depends on another setting)", flush=True)
        raise ProtocolError("param_uia_field_disabled:" + label_substr)
    if not matches and (field_index is not None or below):
        # A two-line row paints its label on one line and its Edit(s) on the
        # next, ~34px lower: 'Overhang speed' with five band Edits (run
        # e4a08beb: row_y=978, nothing within 14px) and the first row of the
        # Speed page (run 0b7886bc: row_y=730, Edit at 764). Only rows that
        # declare it (a field index, or "below": true) get this second pass:
        # for an ordinary row a disabled Edit must NOT fall through to the
        # next row's field. The window stops at +50 so the row after next
        # line (at +64) is out of reach.
        y_lo, y_hi = y_row + 15, y_row + 50
        EnumChildWindows(app.hwnd, collect, None)
    # 2026-11-22 #264: the five overhang degree-band speeds render as ONE
    # labelled row with five inline Edits (Tab.cpp: Line{L("Overhang speed")}
    # ...append_option x5); select left-to-right by field_index instead of
    # failing on the multi-match.
    matches.sort(key=lambda m: m[1][0])
    if len(matches) > 1 and field_index is not None and 0 <= field_index < len(matches):
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
                                  field_index=op.get("field"), below=bool(op.get("below")))
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
            # A list label gets the same candidate treatment as float ops
            # (filament_features passed ['^Wipe tower', 'tower'] straight
            # through and died on list.startswith, run 6b399e48).
            labels = op["label"] if isinstance(op["label"], (tuple, list)) else (op["label"],)
            last = None
            for candidate in labels:
                try:
                    pick_combo_at_label(ui, candidate, op["target"], group_substr=op.get("group"))
                    last = None
                    break
                except ProtocolError as exc:
                    last = exc
            if last is not None:
                raise last
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


def census_param_pages(ui):
    """Probe, not a test case: what the engine's row/group lookups really
    see. Per process tab it dumps every titled panel window (text, rect);
    then a wheel/focus probe (does the page move while the OCR signature
    stays put?) and a popup-geometry probe (is the popup row on screen,
    which window would get the click?). Ends with
    ProtocolError('param_census_done') so the run stops before the save
    phase. 2026-11-23: written after queue18 failed 8 of 9 scenarios, one
    of them with 'no such group title' for a title that was on screen."""
    import ctypes
    import ctypes.wintypes as wt
    import time
    import numpy as np
    from harness import export_util, mix_dialog_util as mdu, winutil
    from . import process_panel as pp

    app = ui.app
    u32 = ctypes.windll.user32

    def say(text):
        print("[census] " + text, flush=True)

    def cls(hwnd):
        return winutil.window_class(hwnd) if hwnd else None

    vp_h = (pp.options_viewport(app) or (None, None))[1]

    def titled(sub=None):
        rows = []
        for t, c, r, h, lx, ly in pp.kids(app):
            if c != "wxWindowNR" or not t.strip() or not u32.IsWindowVisible(h):
                continue
            if sub is not None and sub not in t.lower():
                continue
            # child: is the window a descendant of the options viewport?
            # group_titles() relies on that to keep titles that scrolled
            # above the Process row (r3c).
            rows.append("%r@%d,%d %dx%d child=%s" % (
                t[:44], lx, ly, r[2] - r[0], r[3] - r[1],
                bool(vp_h and u32.IsChild(vp_h, h))))
        return rows

    def sig():
        words = pp.ocr_band(app, psm=3)
        return (tuple(sorted({int(y) // 6 for _w, _x, y, *_r in words})),
                " ".join(w for w, *_ in words)[:64])

    def cursor():
        pt = wt.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def wheel_probe(tag, n, delta):
        vp = pp.options_viewport(app)
        for i in range(n):
            pp.wheel_viewport(app, vp, 1, delta=delta)
            s, head = sig()
            say("%s %s%d: sig=%s head=%r titles=%s focus=%s cursor=%r" % (
                tag, "down" if delta < 0 else "up", i + 1, s, head, titled("layers speed"),
                pp.focus_info(app)[1], cursor()))

    ui.main_input()
    pp.ensure_advanced(app, want=True)
    work = wt.RECT()
    got = u32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    vp = pp.options_viewport(app)
    say("frame=%r work=%r process_row_y=%r viewport=%r band=%r" % (
        pp.frect(app), (work.left, work.top, work.right, work.bottom) if got else None,
        pp.process_row_y(app), vp[0] if vp else None, pp.view_band(app)))
    for tab, hint in (("Quality", "height"), ("Strength", "loops"), ("Speed", "speed"),
                      ("Support", "support"), ("Multimaterial", "tower"), ("Others", "")):
        try:
            ui.main_input()
            ok = pp.click_tab(app, tab, hint)
            ui.pause(1.0)
            counts = {}
            for t, c, r, h, lx, ly in pp.kids(app):
                if lx < 424 and u32.IsWindowVisible(h):
                    counts[c] = counts.get(c, 0) + 1
            say("TAB %s clicked=%s classes=%s" % (tab, ok, counts))
            for row in titled():
                say("   T " + row)
        except Exception as exc:
            say("TAB %s probe failed: %s: %s" % (tab, type(exc).__name__, exc))
    try:
        ui.main_input()
        pp.click_tab(app, "Speed", "speed")
        ui.pause(1.0)
        say("WHEEL start: focus=%s titles=%s" % (pp.focus_info(app)[1], titled("layers speed")))
        wheel_probe("A", 5, -120)
        wheel_probe("A", 5, 120)
    except Exception as exc:
        say("WHEEL probe failed: %s: %s" % (type(exc).__name__, exc))
    try:
        pp.click_tab(app, "Quality", "height")
        cands = pp.find_option_checkbox(app, "Staggered")
        say("CHECKBOX cands=%r" % ([c[0] for c in cands],))
        if cands:
            pp.real_click(cands[0][0])
            say("   after click: focus=%s" % (pp.focus_info(app)[1],))
            wheel_probe("B", 5, -120)
            pp.focus_off_edit(app, why="census")
            say("   after focus_off_edit: focus=%s" % (pp.focus_info(app)[1],))
            wheel_probe("B", 3, -120)
    except Exception as exc:
        say("CHECKBOX probe failed: %s: %s" % (type(exc).__name__, exc))
    try:
        pp.click_tab(app, "Others", "")
        pp.scroll_group_into_view(app, "Special mode")

        def open_and_report(tag, click):
            r, _h, cur = pp.find_option_combo_seq(app, ("By", "Layer"), None)
            if not r:
                say("   %s: combo not found" % tag)
                return
            winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, app.hwnd)
            popup = None
            for _ in range(20):
                popup = export_util.wait_popup(app.pid, timeout_s=0.5)
                if popup:
                    break
            if not popup:
                say("   %s: combo rect=%r text=%r -> no popup" % (tag, r, cur))
                return
            pr, ph = popup[2], popup[3]
            time.sleep(0.8)
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3)
            hits = pp.popup_line_hits(words, "by object")
            say("   %s: combo rect=%r popup rect=%r capture=%dx%d words=%r hits=%r" % (
                tag, r, pr, w, hgt, [(t, x, y) for t, x, y, *_ in words], hits))
            for cx_, cy_, _line in hits[:1]:
                x, y = pr[0] + cx_, pr[1] + cy_
                target = winutil.window_from_screen_point(x, y)
                say("      click point (%d,%d) -> class=%s rect=%r (popup class=%s)" % (
                    x, y, cls(target), winutil.window_rect(target) if target else None, cls(ph)))
                if click:
                    winutil.msg_click_screen(x, y)
                    time.sleep(2.5)
                    _r2, _h2, cur2 = pp.find_option_combo_seq(app, ("By", "Object"), None)
                    say("      clicked -> combo text now %r" % (cur2,))

        open_and_report("at-edge", click=False)
        try:
            from PIL import ImageGrab
            ImageGrab.grab(all_screens=True).save(ui.artifacts / "param_failure.png")
            say("   screen shot with the popup open saved")
        except Exception as exc:
            say("   screen shot failed: %s: %s" % (type(exc).__name__, exc))
        mdu._send_keys([(0x1B, False), (0x1B, True)])
        time.sleep(0.8)
        # r3c: the engine's own path - it parks the row before opening
        # anything, refuses to click off-screen and verifies by the combo's
        # window text.
        try:
            res = pp.set_combo_by_popup(app, ("By", "Layer"), "By object",
                                        group_substr="Special mode", log="[census]")
            say("   engine set_combo_by_popup -> %r" % (res,))
            _r3, _h3, cur3 = pp.find_option_combo_seq(app, ("By", "Object"), None)
            say("   combo located by 'By Object' afterwards: rect=%r text=%r" % (_r3, cur3))
        except Exception as exc:
            say("   engine set_combo_by_popup failed: %s: %s" % (type(exc).__name__, exc))
    except Exception as exc:
        say("POPUP probe failed: %s: %s" % (type(exc).__name__, exc))
    raise ProtocolError("param_census_done")
