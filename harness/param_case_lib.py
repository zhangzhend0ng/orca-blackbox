"""Shared machinery for the Feishu 常用工艺参数 supplement cases.

Each case = a values dict (config keys the case may change, with target
values) plus G-code expectations the existing analyzers can prove. This
library builds verify_business implementations from such specs and keeps
the change-scope registry the settings-preservation check admits."""
from decimal import Decimal
import re

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


def _find_phrase_row_any(app, phrase, group_substr=None):
    """(row y, matched candidate) of a painted label that may span several OCR words.

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

    if group_substr and not pp.scroll_group_into_view(app, group_substr):
        # A group name that matches no title used to be ignored: span None
        # turned the search into an unconstrained page scan that edited the
        # first same-named row it met (fa706g3 review D2, 2026-11-23). A
        # missing group is a wrong op, not a reason to look everywhere.
        print("[param-phrase] group %r has no title on this page -> not "
              "looking for %r" % (group_substr, phrase), flush=True)
        return None, None
    # `phrase` may be a str or a list of candidates. All candidates are
    # looked for in ONE scan, in the given order. Until r4 every candidate
    # got a scan of its own, so a candidate that is not on the page (the
    # atlas label 'Outer wall line width') cost a whole-page search in both
    # directions before the plain one was even tried: line_width_all run
    # 4149046c spent ten minutes on three such candidates.
    names = [phrase] if isinstance(phrase, str) else [p for p in phrase if p]
    cands = []
    for name in names:
        anchored = name.startswith("^")
        text = name[1:] if anchored else name
        cands.append((name, anchored, text, text.lower().split()))

    def hit(i, words, cand):
        _name, anchored, text, want = cand
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
        return tail.startswith(text.lower())

    what = names[0] if len(names) == 1 else names
    stall = pp._StallGuard(app, "phrase %r%s" % (what, " in %r" % group_substr if group_substr else ""))
    found = matched = None
    words = []
    for direction in (-120, 120):
        stall.reset()
        started = time.monotonic()
        last_band = None
        way = "down" if direction < 0 else "up"
        for _ in range(pp.SCAN_NOTCHES):
            if time.monotonic() - started > pp.SCAN_SECONDS:
                print("[param-phrase] %ss cap reached scanning %s for %r" % (
                    pp.SCAN_SECONDS, way, what), flush=True)
                break
            # Re-read every step: the span is in client coordinates and the
            # page moves under it. Frozen at the start it rejected the
            # group's own rows once they had scrolled above the title's
            # starting position (queue18).
            span = pp.group_span(app, group_substr) if group_substr else None
            words = pp.ocr_band(app, psm=3)
            # The band on every change, like find_option_row: without it a
            # failed scan left nothing to read (queue19 brim / filament_features).
            band = " ".join(w for w, *_ in words)[:120]
            if band != last_band:
                print("[param-phrase] %r%s %s band: %r" % (
                    what, " in %r" % group_substr if group_substr else "", way, band), flush=True)
                last_band = band
            for i in range(len(words)):
                if span is not None and not (span[0] <= words[i][2] < span[1]):
                    continue
                for cand in cands:          # the first candidate in the op's order wins
                    if hit(i, words, cand):
                        found = words[i][2] + words[i][4] // 2
                        matched = cand[0]
                        break
                if found is not None:
                    break
            if found is not None:
                print("[param-phrase] %r found %s at y=%r span=%r" % (
                    matched, way, found, span), flush=True)
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
        print("[param-phrase] not found: %r | last band: %s" % (
            what, " ".join(w for w, *_ in words)[:160]), flush=True)
    return found, matched


def _find_phrase_row(app, phrase, group_substr=None):
    """Row y for `phrase` (a str); see _find_phrase_row_any."""
    return _find_phrase_row_any(app, phrase, group_substr)[0]


def _is_multiline(wu, handle, value=None):
    """True when the Edit carries ES_MULTILINE (GWL_STYLE bit 0x0004). With
    the style unreadable (no user32 on a fake) the old rule decides: a value
    with no number in it is text."""
    user32 = getattr(wu, "user32", None)
    get_style = getattr(user32, "GetWindowLongW", None)
    if get_style is not None:
        try:
            return bool(get_style(handle, -16) & 0x0004)
        except Exception:  # noqa: BLE001
            pass
    found = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return found is None


EDIT_ROOM = 12   # px of work area an Edit needs below it before it is driven


def _park_field(ui, bounds):
    """Notches the options page was wheeled DOWN so the Edit at screen
    `bounds` has EDIT_ROOM px of work area below it (0 = it already had, or
    nothing could be measured). The caller locates its row again whenever
    this returns > 0: the page moved."""
    from . import process_panel as pp
    try:
        work = pp.work_area()
        viewport = pp.options_viewport(ui.app)
    except Exception:  # noqa: BLE001 - a fake without the calls keeps the old rule
        return 0
    if not work or not viewport:
        return 0
    if not (isinstance(work[3], int) and work[3] > 0
            and isinstance(bounds[3], int) and bounds[3] > 0):
        return 0          # nothing measured (a fake): keep the old rule
    short = EDIT_ROOM - (work[3] - bounds[3])
    if short <= 0:
        return 0
    notches = min(8, -(-short // pp.WHEEL_STEP_PX))
    pp.wheel_viewport(ui.app, viewport, notches, delta=-120)
    print(f"[param-uia] edit bottom {bounds[3]} had {work[3] - bounds[3]}px "
          f"above the work-area bottom {work[3]} -> {notches} notches", flush=True)
    getattr(ui, "pause", lambda _seconds: None)(1.0)
    return notches


def uia_set_float(ui, label_substr, value, group_substr=None, field_index=None, below=False, _parked=0):
    """Set a sidebar float Edit: OCR locates the painted row (OG_CustomCtrl
    draws row labels without HWNDs - only group headers are windows, the
    f5acdb1a census), then the visible Edit whose row-y matches is driven
    through the proven ui.edit commit. No x-column calibration (the m4g
    band does not hold on every page - runs 47bccc5a+)."""
    from win32gui import EnumChildWindows, IsWindowVisible, IsWindowEnabled

    wu, app = ui.wu, ui.app
    # `label_substr` may be a list of candidates: they are searched in ONE
    # scan (_find_phrase_row_any). From here on it is the label that matched.
    y_row, matched = _find_phrase_row_any(app, label_substr, group_substr)
    if y_row is None:
        label_substr = (label_substr if isinstance(label_substr, str) else label_substr[0])
        raise ProtocolError("param_row:" + label_substr)
    label_substr = matched
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
    declared = field_index is not None or below
    if greyed and not declared:
        # A greyed field means the row is disabled by another setting
        # (Brim width under Brim type = Auto). Say so instead of reporting
        # a bare "0 edits" that reads like a lookup miss.
        print(f"[param-uia] row '{label_substr}' y={y_row}: field is disabled "
              f"(depends on another setting)", flush=True)
        raise ProtocolError("param_uia_field_disabled:" + label_substr)
    if not matches:
        # A two-line row paints its label on one line and its Edit(s) on
        # the other, the control centred on the ROW: the Edit sits half a
        # row-pitch (about 15px on 2.4.0) off the matched line; a multi-field
        # row's Edits sit ~34px below the label line (run e4a08beb).
        # - declared rows (a field index, or "below"): the whole line below
        #   [y+15, y+50], or the line above when nothing is below;
        # - ordinary rows: exactly ONE Edit 7..23px off the line (fa706g3
        #   review D4; find_option_checkbox does the same for boxes). The next
        #   single-line row's Edit is 30px away and cannot qualify, so an
        #   ordinary row whose Edit is simply missing still fails below.
        windows = ([(y_row + 15, y_row + 50), (y_row - 50, y_row - 15)] if declared
                   else [(y_row - 23, y_row - 7), (y_row + 7, y_row + 23)])
        for y_lo, y_hi in windows:
            EnumChildWindows(app.hwnd, collect, None)
            if matches:
                break

    def survey_and_raise(what):
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
        raise ProtocolError(what)

    # 2026-11-22 #264: the five overhang degree-band speeds render as ONE
    # labelled row with five inline Edits (Tab.cpp: Line{L("Overhang speed")}
    # ...append_option x5); select left-to-right by field_index.
    if field_index is not None:
        # A `field` row is ONE label with its Edits stacked VERTICALLY
        # around it: VM run 210446b4 shows 'Overhang speed' with five
        # boxes at a 27px pitch, the label centred on the block, so field
        # 0 is the second box ABOVE the label line. Every earlier version
        # looked only below the label and typed all four values into the
        # third box. Field i is the i-th Edit from the top of the block.
        matches = []
        y_lo, y_hi = y_row - 60, y_row + 60
        EnumChildWindows(app.hwnd, collect, None)
        matches.sort(key=lambda m: m[1][1])          # top to bottom
    else:
        matches.sort(key=lambda m: m[1][0])
    if field_index is not None:
        # The declared index must exist. With fewer Edits than the index
        # needs the old code fell through to "exactly one match" and drove
        # that Edit: every op of runs 7f9beea4 / 50798c59 typed into the
        # SAME overhang Edit (Mac audit, 2026-11-23).
        if not (0 <= field_index < len(matches)):
            survey_and_raise("param_uia_field:" + label_substr + ":"
                             + str(len(matches)) + "<=field" + str(field_index))
        print(f"[param-uia] row '{label_substr}' has {len(matches)} edits; "
              f"driving field[{field_index}]", flush=True)
        handle, bounds = matches[field_index]
    elif len(matches) == 1:
        handle, bounds = matches[0]
    else:
        survey_and_raise("param_uia_field:" + label_substr + ":" + str(len(matches)))
    # A stacked field can sit under the bottom edge of the page although
    # Win32 still calls it visible: fa706g3 run 4491e40 ('Overhang speed',
    # field 3 of 4, the label at client y 1005) died on edit_outside_client,
    # while the guest's taller window never showed it. Give it room, then
    # locate the row again on the moved page (at most three times).
    if _parked < 3 and _park_field(ui, bounds):
        return uia_set_float(ui, label_substr, value, group_substr, field_index, below,
                             _parked=_parked + 1)
    x = (bounds[0] + bounds[2]) // 2 - origin_x
    y = (bounds[1] + bounds[3]) // 2 - origin_y
    from decimal import Decimal as _D, InvalidOperation as _Inv

    def _num(text):
        # The sign is part of the value: the old digit filter dropped it,
        # so "-0.1" read back as "0.1" passed (Mac audit, 2026-11-23).
        found = re.search(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))
        try:
            return _D(found.group(0)) if found else None
        except _Inv:
            return None

    if _is_multiline(wu, handle, value):
        # A TEXT field (the filename format of #296) is multi-line: Enter is
        # a newline in it, not a commit - fa run a9cce05e saved
        # '{input_filename_base}_{plate_name}.gcode\n'. The value commits
        # when the field loses focus; the readback is the whole text. The
        # CONTROL decides (ES_MULTILINE), not the value: a text with a digit
        # in it used to take the Enter branch (fa review of 53278b8).
        receipt = ui.edit(x, y, str(value), enter=False)
        from . import process_panel as pp
        focus = pp.focus_off_edit(app, "text field commit")
        ui.pause(2.0)
        if focus == "Edit":
            raise ProtocolError("param_text_field_focus_stuck:" + label_substr)
        after = ui.wu.edit_text(handle)
        if (receipt["target_hwnd"] != handle
                or after.replace("\r\n", "\n") != str(value)):
            raise ProtocolError("param_uia_readback:" + label_substr + ":" + repr(after)[:60])
        return
    receipt = ui.edit(x, y, str(value))
    if (receipt["target_hwnd"] != handle
            or _num(receipt["after_text"]) != _num(value)):
        raise ProtocolError("param_uia_readback:" + label_substr + ":" + repr(receipt.get("after_text"))[:40])


def _dialog_gone(ui, dlg, timeout_s):
    """True once the main window is enabled again and `dlg` no longer
    exists. Polls every 0.25 s up to `timeout_s`."""
    import time
    from . import winutil

    app = ui.app
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        if winutil.user32.IsWindowEnabled(app.hwnd) and not winutil.user32.IsWindow(dlg):
            return time.monotonic() - started
        ui.pause(0.25)
    return None


def _page_settled(ui, timeout_s=15.0):
    """Wait until the panel's child windows (handles, texts, rects) read
    the same twice 0.5 s apart - a confirmed edit rebuilds the page, and
    locating a row on a half-rebuilt page hits the wrong one."""
    import time
    from . import process_panel as pp

    def signature():
        return [(t, c, r, h) for t, c, r, h, _lx, _ly in pp.kids(ui.app)]

    started = time.monotonic()
    last = signature()
    while time.monotonic() - started < timeout_s:
        ui.pause(0.5)
        now = signature()
        if now == last:
            return True
        last = now
    return False


def settle_dialog(ui, known, answer=None, expect=None):
    """(hwnd, text) of the dialog the app opened right after an op, or
    (None, ''). `answer` names the button to press ('Yes'); `expect` is a
    piece of the question the op expects (e.g. 'Spiral mode'). A box whose
    text does not carry `expect` is closed, never answered: a rule meant for
    one question must not say Yes to another.

    Spiral vase (VM run 49723134): ticking the box makes the app ask
    whether to switch wall loops / top layers / sparse infill to vase
    values (ConfigManipulation.cpp:321-351). The old code waited for the
    combo popup - export_util.wait_popup is a top-level wxWindowNR 'panel',
    which a message box never is - so the box stayed open and the next
    guard raised main_window_modal_blocked. Closing it means No: the app
    then switches spiral mode back off, which is why the op names the
    answer.

    The box is found by its EFFECT - a modal disables the main window, the
    same fact the next guard would trip on - and then taken by class
    '#32770' owned by the main window. It is wx's own dialog: its buttons
    are OWNER-DRAWN wxWindowNR windows, not 'Button's (VM run d8cec0d4:
    children Static / wxWindowNR x3; the three ways before that - Button
    children, a native task dialog's TDM_CLICK_BUTTON, WM_COMMAND and a
    real Enter - could not work and each cost a run)."""
    from . import export_util, mixing_util, process_panel as pp, winutil
    import time

    app = ui.app
    dlg = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not winutil.user32.IsWindowEnabled(app.hwnd):
            new = [w for w in mixing_util.toplevel(app.pid)
                   if w[3] not in known and w[3] != app.hwnd
                   and (w[2][3] - w[2][1]) < 400]
            owned = [w for w in new if w[0] == "#32770"
                     and winutil.user32.GetWindow(w[3], 4) == app.hwnd]   # GW_OWNER
            if owned or new:
                dlg = (owned or new)[0][3]
                break
        time.sleep(0.25)
    if dlg is None:
        popup = export_util.wait_popup(app.pid, timeout_s=0.8)
        if popup:
            winutil.user32.PostMessageW(popup[3], 0x0010, 0, 0)  # WM_CLOSE
            ui.pause(0.6)
        return None, ""
    body = pp.dialog_body(app.pid, dlg)
    kids = mixing_util.children(dlg)
    buttons = [b for b in kids if b[1] in ("Button", "wxWindowNR") and b[0].strip()]
    if not buttons:
        small = sorted((b for b in kids if b[1] != "Static"
                        and (b[2][3] - b[2][1]) <= 40 and (b[2][2] - b[2][0]) <= 160),
                       key=lambda b: b[2][0])
        if len(small) == 2:
            buttons = small
    try:
        cls = winutil.window_class(dlg)          # for the log only
    except Exception:  # noqa: BLE001
        cls = "?"
    print("[param case] dialog after the checkbox: %r; class %r; children %r; buttons %r" % (
        body[:160], cls, [(t, c) for t, c, _r, _h in kids][:12],
        [(t, c, r) for t, c, r, _h in buttons]), flush=True)

    def close(why):
        print("[param case] %s - closing it (WM_CLOSE)" % why, flush=True)
        winutil.user32.PostMessageW(dlg, 0x0010, 0, 0)  # WM_CLOSE
        gone = _dialog_gone(ui, dlg, 8.0)
        print("[param case] box gone: %s" % ("after %.1f s" % gone if gone is not None else "NO"),
              flush=True)

    want = answer.replace("&", "").strip().lower() if answer else None
    if want and expect and expect.lower() not in body.lower():
        close("the box is not the expected one (%r is not in its text)" % expect)
        return dlg, body
    hit = how = None
    if want:
        for _t, _c, r, h in buttons:
            if _t.replace("&", "").strip().lower().startswith(want):
                hit, how = (r, h), "text"
        if hit is None and expect and len(buttons) == 2 and want in ("yes", "no"):
            # a native box labels its buttons in the Windows language
            # ('是/否'), so the text rule misses: in a two-button Yes/No
            # box Yes is the first one. Only for an op that named the
            # answer AND the question - never a guess on an unnamed box.
            first = buttons[0][0].replace("&", "").strip().lower()
            first_is_no = first.startswith("no") or first.startswith("否")
            index = (want == "no") != first_is_no
            hit, how = (buttons[int(index)][2], buttons[int(index)][3]), "position"
    if hit is not None:
        (x0, y0, x1, y1), _button = hit
        print("[param case] answering %r by %s: click (%d,%d)" % (
            answer, how, (x0 + x1) // 2, (y0 + y1) // 2), flush=True)
        winutil.real_click_screen((x0 + x1) // 2, (y0 + y1) // 2)
        gone = _dialog_gone(ui, dlg, 10.0)
        if gone is None:
            raise ProtocolError("param_dialog_not_closed:" + str(answer))
        print("[param case] box gone after %.1f s; page settled: %s" % (
            gone, _page_settled(ui)), flush=True)
        return dlg, body
    if want in ("yes", "no") and expect and not any(k[1] == "Button" for k in kids):
        # No button window to click. A native box of this app would be a
        # TASK DIALOG (buttons drawn in a DirectUI child, WM_COMMAND
        # ignored) and the guest keeps the app out of the foreground, so no
        # real key ever reaches it. Each way below is checked by the main
        # window being enabled again; WM_CLOSE (= No) is the last resort.
        command = 6 if want == "yes" else 7                 # IDYES / IDNO

        def answered(how):
            gone = _dialog_gone(ui, dlg, 2.0)
            if gone is not None:
                print("[param case] answered %r by %s; box gone after %.1f s" % (
                    answer, how, gone), flush=True)
                return True
            return False

        winutil.user32.PostMessageW(dlg, 0x046A, command, 0)    # TDM_CLICK_BUTTON = WM_USER + 102
        if answered("TDM_CLICK_BUTTON (task dialog)"):
            _page_settled(ui)
            return dlg, body
        winutil.user32.PostMessageW(dlg, 0x0111, command, 0)   # WM_COMMAND
        if answered("WM_COMMAND"):
            _page_settled(ui)
            return dlg, body
        if want == "yes":
            for message in (0x0100, 0x0101):                   # WM_KEYDOWN / WM_KEYUP
                winutil.user32.PostMessageW(dlg, message, 0x0D, 0)   # VK_RETURN: default button
            if answered("a posted Enter"):
                _page_settled(ui)
                return dlg, body
            from harness import mix_dialog_util as mdu
            if winutil.force_set_foreground(dlg):
                ui.pause(0.5)
                mdu._send_keys([(0x0D, False), (0x0D, True)])   # a real Enter, only in front
                if answered("a real Enter"):
                    _page_settled(ui)
                    return dlg, body
        close("no way to answer the box")
    else:
        close("no answer named for this box" if not want else "no expected question named")
    return dlg, body


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
            # All label candidates in ONE scan, first match in the op's
            # order (_find_phrase_row_any). The per-candidate loop this
            # replaces paid a whole-page search for every candidate that is
            # not on the page.
            # `labels` must come from THIS op: the first version of this
            # branch used a name that only the rowcombo branch defined, so a
            # float op after a rowcombo op edited the rowcombo's label (fa
            # run f4b87b67: 'point distance' searched for 'Fuzzy skin') and
            # any other float op died on a NameError.
            labels = op["label"] if isinstance(op["label"], (tuple, list)) else (op["label"],)
            uia_set_float(ui, labels, str(op["value"]), group_substr=op.get("group"),
                          field_index=op.get("field"), below=bool(op.get("below")))
            pp.neutralize_focus(app)
        elif kind == "checkbox":
            # 2026-11-23: enabling some options (Spiral vase, run c6584b3e)
            # pops a modal that trips the next guard
            # (main_window_modal_blocked) - see settle_dialog.
            known_dialogs = pp.top_dialog_set(app)
            ok = pp.set_option_checkbox(app, op["label"], op["value"], group_substr=op.get("group"))
            # set_option_checkbox returns (now_on, rect); for want=False a
            # SUCCESSFUL uncheck returns ok[0]=False - the old `is True` check
            # rejected every unchecked-success (seam_wipe 'Role' att0 did
            # 0.21->0.06 then raised, run 7cb0e911).
            if not (isinstance(ok, tuple) and ok[0] == op["value"]):
                raise ProtocolError("param_checkbox:" + op["label"])
            settled = settle_dialog(ui, known_dialogs, op.get("answer"), op.get("dialog"))
            if settled[0] is not None:
                # A box was answered or closed. Answered No (or closed =
                # No), the app puts the setting back (ConfigManipulation
                # .cpp:350) while the op above still says it is set: read
                # the box again on the settled page (fa review, Q1c).
                ui.main_input()
                found = pp.find_option_checkbox(app, op["label"], op.get("group"))
                if found:
                    now_on = pp.checked_state(app, found[0][0]) > pp.CHECKED_FRACTION
                    print("[param case] checkbox %r reads %s after the box" % (
                        op["label"], now_on), flush=True)
                    if now_on != op["value"]:
                        raise ProtocolError("param_checkbox:" + op["label"] + ":reverted")
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


def _census_pages_full(ui):
    """Full probe (only when CENSUS_FULL): what the engine's row/group lookups really
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
    from harness import export_util, mix_dialog_util as mdu, mixing_util, winutil
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

        def open_and_report(tag, locate):
            """Open the combo whose painted value is `locate`; report the
            popup geometry and the window a click on 'By object' would hit.
            Returns (popup_rect, popup_hwnd, combo_rect) or None."""
            r, _h, cur = pp.find_option_combo_seq(app, locate, None)
            if not r:
                say("   %s: combo %r not found" % (tag, locate))
                return None
            winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2, app.hwnd)
            popup = None
            for _ in range(20):
                popup = export_util.wait_popup(app.pid, timeout_s=0.5)
                if popup:
                    break
            if not popup:
                say("   %s: combo rect=%r text=%r -> NO popup within 10s" % (tag, r, cur))
                return None
            pr, ph = popup[2], popup[3]
            time.sleep(0.8)
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3)
            hits = pp.popup_line_hits(words, "by object")
            say("   %s: combo rect=%r popup rect=%r capture=%dx%d words=%r" % (
                tag, r, pr, w, hgt, [(t, x, y) for t, x, y, *_ in words]))
            for cx_, cy_, _line in hits[:1]:
                x, y = pr[0] + cx_, pr[1] + cy_
                target = winutil.window_from_screen_point(x, y)
                say("      'By object' click point (%d,%d) -> class=%s rect=%r (popup class=%s)" % (
                    x, y, cls(target), winutil.window_rect(target) if target else None, cls(ph)))
            return pr, ph, r

        def close(opened):
            if opened:
                pr, ph, r = opened
                say("   close_popup -> %r" % (pp.close_popup(
                    app, ph, ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)),))

        # The engine's own path first, on a control nothing has touched: it
        # parks the row before opening anything, refuses to click off-screen
        # and verifies by the combo's window text.
        try:
            res = pp.set_combo_by_popup(app, ("By", "Layer"), "By object",
                                        group_substr="Special mode", log="[census]")
            say("   engine set_combo_by_popup -> %r" % (res,))
        except Exception as exc:
            say("   engine set_combo_by_popup failed: %s: %s" % (type(exc).__name__, exc))
        _r3, _h3, cur3 = pp.find_option_combo_seq(app, ("By", "Object"), None)
        say("   combo located by 'By Object' afterwards: rect=%r text=%r" % (_r3, cur3))
        # Then the raw geometry where the row is now, and whether a popup
        # that was just closed can be reopened at once (census e80c899c:
        # after a bare ESC the next click opened nothing).
        opened = open_and_report("after-commit", ("By", "Object"))
        if opened:
            try:
                from PIL import ImageGrab
                ImageGrab.grab(all_screens=True).save(ui.artifacts / "param_failure.png")
                say("   screen shot with the popup open saved")
            except Exception as exc:
                say("   screen shot failed: %s: %s" % (type(exc).__name__, exc))
        close(opened)
        opened = open_and_report("reopened-after-close", ("By", "Object"))
        close(opened)
        # 'Brim type' is a painted-value combo (no ComboBox hwnd; its value
        # window is a titled wxWindowNR 120 wide). Three runs OCR'd its popup
        # as empty (f323be97, 5a73aee3 and queue17's brim). Open it the way
        # pick_combo_at_label does and dump every top-level window of the
        # app plus the capture of whatever is new.
        try:
            pp.scroll_group_into_view(app, "Brim")
            y_row = _find_phrase_row(app, "^Brim type", None)
            say("BRIM '^Brim type' row y=%r" % (y_row,))
            if y_row is not None:
                left = winutil.window_rect(_canvas_hwnd(ui))[0]
                cx, cy = left - 90, y_row + pp.client_origin(app)[1]
                target = winutil.window_from_screen_point(cx, cy)
                buf = ctypes.create_unicode_buffer(128)
                u32.GetWindowTextW(target, buf, 128) if target else None
                say("   value-zone point (%d,%d) -> class=%s rect=%r text=%r" % (
                    cx, cy, cls(target), winutil.window_rect(target) if target else None, buf.value))
                before = {w[3] for w in mixing_util.toplevel(app.pid)}
                winutil.msg_click_screen(cx, cy, app.hwnd)
                time.sleep(1.5)
                after = mixing_util.toplevel(app.pid)
                new = [w for w in after if w[3] not in before]
                say("   app top-levels: %r" % ([(c, t, r) for c, t, r, _h in after],))
                for c, t, r, h in new:
                    try:
                        w, hgt, bgra = winutil.capture_window(h)
                        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
                        words = mdu.ocr_words_img(img, scale=3)
                        say("   NEW top-level class=%s text=%r rect=%r hwnd=%s capture=%dx%d "
                            "words=%r" % (c, t, r, h, w, hgt, [(a, b, d) for a, b, d, *_ in words]))
                    except Exception as exc:
                        say("   NEW top-level class=%s text=%r rect=%r hwnd=%s capture failed: %s: %s" % (
                            c, t, r, h, type(exc).__name__, exc))
                try:
                    from PIL import ImageGrab
                    ImageGrab.grab(all_screens=True).save(ui.artifacts / "param_failure.png")
                    say("   screen shot with the Brim popup open saved")
                except Exception as exc:
                    say("   screen shot failed: %s: %s" % (type(exc).__name__, exc))
                for c, t, r, h in new:
                    say("   close_popup(%r) -> %r" % (t, pp.close_popup(app, h, (cx, cy))))
        except Exception as exc:
            say("BRIM probe failed: %s: %s" % (type(exc).__name__, exc))
    except Exception as exc:
        say("POPUP probe failed: %s: %s" % (type(exc).__name__, exc))
    raise ProtocolError("param_census_done")


# Also run the wheel / focus / Print-sequence probes of the first censuses.
CENSUS_FULL = False
# Also dump every line of every page (see census_param_pages); ~4 minutes.
CENSUS_ROWS_ALL = True
# Short names of the combo ops whose popup is opened and listed (about 28s
# per popup); empty = none. The x_ rows are probe-only rows listed in
# census_param_pages. The 2026-11-23 popups are recorded in
# tools/param_ui_popups_2.4.0.json.
CENSUS_PICK = ()
#        = ("support_basic", "tree_support", "skirt", "x_support_base", "x_support_iface")


def census_param_pages(ui):
    """Probe, not a test case: what the engine's row/group lookups really
    see, and what every combo op's popup REALLY offers.

    The source atlas is not the build (census c101c0f4: 'Initial layer speed'
    vs 'First layer speed'; f1c5433b: the Brim type popup says 'Outer brim
    only' where the op looked for 'Outer only'). So for each combo op of
    PARAM_OPS this opens the popup the way the engine does, lists its rows
    and says whether the op's target is among them. Ends with
    ProtocolError('param_census_done') so the run stops before the save
    phase. Refresh with: scenario uia_param_census (about 5 minutes)."""
    import ctypes
    import ctypes.wintypes as wt
    import json
    import time
    import numpy as np
    from win32gui import EnumChildWindows, IsWindowVisible
    from harness import export_util, mix_dialog_util as mdu, mixing_util, winutil
    from . import process_panel as pp
    from .native_script_baseline import PARAM_OPS

    app, wu, u32 = ui.app, ui.wu, ctypes.windll.user32
    hints = {"Quality": "height", "Strength": "loops", "Speed": "speed",
             "Support": "support", "Multimaterial": "tower", "Others": ""}

    def say(text):
        print("[census] " + text, flush=True)

    def cls(hwnd):
        return winutil.window_class(hwnd) if hwnd else None

    def titled():
        vp_h = (pp.options_viewport(app) or (None, None))[1]
        out = []
        for t, c, r, h, lx, ly in pp.kids(app):
            if c == "wxWindowNR" and t.strip() and t.strip() != "panel" \
                    and u32.IsWindowVisible(h) and (r[2] - r[0]) >= 300 \
                    and lx < 60 and (r[3] - r[1]) <= 30:
                out.append("%r@%d" % (t[:40], ly))
        return out

    ui.main_input()
    pp.ensure_advanced(app, want=True)
    work = wt.RECT()
    got = u32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    say("frame=%r client_origin=%r work=%r process_row_y=%r" % (
        pp.frect(app), pp.client_origin(app),
        (work.left, work.top, work.right, work.bottom) if got else None, pp.process_row_y(app)))

    combos, tab = [], None
    for scenario, ops in sorted(PARAM_OPS.items()):
        for op in ops:
            tab = op.get("tab") or tab
            if op["op"] in ("combo", "rowcombo"):
                combos.append((scenario.replace("uia_param_", ""), tab, op["op"],
                               op.get("label") or op.get("current"), op.get("target"), op.get("group")))
    # Rows no op names yet (census 67690ed4): the extruder selection of the
    # support body / interface, the interface pattern, the draft shield.
    combos += [
        ("x_support_base", "Support", "rowcombo", "^Support/raft base", "?", "Filament for Supports"),
        ("x_support_iface", "Support", "rowcombo", "^Support/raft interface", "?", "Filament for Supports"),
        ("x_support_pattern", "Support", "rowcombo", "Interface pattern", "?", "Advanced"),
        ("x_draft_shield", "Others", "rowcombo", "Draft shield", "?", "Skirt"),
    ]
    combos.sort(key=lambda c: (list(hints).index(c[1]) if c[1] in hints else 99, c[0]))
    # A full sweep is ~28s per popup: only the names in CENSUS_PICK are
    # opened (none by default).
    combos = [c for c in combos if c[0] in CENSUS_PICK]
    shots = []
    support_enabled = False
    current_tab = None
    for scenario, tab, kind, locate, target, group in combos:
        try:
            if tab != current_tab:
                ui.main_input()
                clicked = pp.click_tab(app, tab, hints.get(tab, ""))
                ui.pause(1.0)
                current_tab = tab
                say("TAB %s clicked=%s titles=%s" % (tab, clicked, titled()))
            if scenario.startswith("x_support") and not support_enabled:
                # the support rows are greyed until support is on: a click
                # on a greyed value opens nothing (census 40989dec)
                say("   enable support -> %r" % (pp.set_option_checkbox(
                    app, "Enable", True, group_substr="Support")[0],))
                support_enabled = True
            if group:
                pp.scroll_group_into_view(app, group)
            if kind == "rowcombo":
                label = locate[0] if isinstance(locate, (tuple, list)) else locate
                y = _find_phrase_row(app, label, None)
                if y is None:
                    say("POPUP %-18s %s %r target=%r: ROW NOT FOUND" % (scenario, tab, label, target))
                    continue
                left = winutil.window_rect(_canvas_hwnd(ui))[0]
                oy = pp.client_origin(app)[1]
                combo = []

                def collect(handle, _):
                    if (wu.window_class(handle) == "ComboBox" and IsWindowVisible(handle)
                            and wu._window_pid(handle) == app.pid):
                        b = wu.window_rect(handle)
                        if abs((b[1] + b[3]) // 2 - oy - y) <= 14 and (b[0] + b[2]) // 2 < left:
                            combo.append(b)
                    return True

                EnumChildWindows(app.hwnd, collect, None)
                if len(combo) == 1:
                    b = combo[0]
                    point, how = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2), "ComboBox"
                else:
                    point, how = (left - 90, y + oy), "value-zone"
                shown = label
            else:
                seq = (tuple(locate.lower().split()) if isinstance(locate, str)
                       else tuple(locate))
                r, h, _cur = pp.find_option_combo_seq(app, seq, group)
                word, yrow = pp.find_option_row_seq(app, seq, group)
                say("      locate %r: word=%r y=%r -> hwnd class=%s rect=%r text=%r" % (
                    seq, word, yrow, cls(h), r, _cur))
                if not r:
                    say("POPUP %-18s %s %r target=%r: VALUE NOT FOUND" % (scenario, tab, locate, target))
                    continue
                point, how, shown = ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2), cls(h), locate
            popup = None
            for click in (1, 2):   # a just-dismissed popup can swallow a click
                winutil.msg_click_screen(point[0], point[1], app.hwnd)
                for _ in range(12 if click == 1 else 16):
                    popup = export_util.wait_popup(app.pid, timeout_s=0.5)
                    if popup:
                        break
                if popup:
                    break
                time.sleep(0.6)
            if not popup:
                say("POPUP %-18s %s %r target=%r click=%r via=%s: NO POPUP" % (
                    scenario, tab, shown, target, point, how))
                continue
            pr, ph = popup[2], popup[3]
            time.sleep(0.8)
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3)
            lines = {}
            for t, x, yw, _ww, _hh in words:
                key = next((k for k in lines if abs(k - yw) <= 10), yw)
                lines.setdefault(key, []).append((x, t))
            items = [" ".join(t for _x, t in sorted(v)) for _k, v in sorted(lines.items())]
            hit = bool(pp.popup_line_hits(words, target)) if target else False
            shots.append(("%s %s %r -> %r" % (scenario, tab, shown, target),
                          img[:, :, ::-1].copy()))
            say("POPUP %-18s %s %r target=%r click=%r via=%s popup=%r hit=%s" % (
                scenario, tab, shown, target, point, how, pr, hit))
            say("      items=%r" % (items,))
            say("      words=%r" % ([(t, x, yw) for t, x, yw, *_ in words][:40],))
            say("      close_popup -> %r" % (pp.close_popup(app, ph, point),))
            time.sleep(0.5)
        except Exception as exc:
            say("POPUP %-18s failed: %s: %s" % (scenario, type(exc).__name__, exc))
    # Row labels of the groups whose ops were authored from the source
    # atlas: three OCR'd views per group, two notches apart.
    for tab, group in (("Multimaterial", "Filament for Features"),
                       ("Support", "Filament for Supports"), ("Support", "Advanced"),
                       ("Others", "Skirt")):
        try:
            if tab != current_tab:
                ui.main_input()
                pp.click_tab(app, tab, hints.get(tab, ""))
                ui.pause(1.0)
                current_tab = tab
            pp.scroll_group_into_view(app, group)
            for view in range(3):
                words = pp.ocr_band(app, psm=3)
                lines = {}
                for t, x, yw, _ww, _hh in words:
                    key = next((k for k in lines if abs(k - yw) <= 10), yw)
                    lines.setdefault(key, []).append((x, t))
                say("ROWS %s %r view%d: %r" % (tab, group, view, [
                    " ".join(t for _x, t in sorted(v)) for _k, v in sorted(lines.items())]))
                pp.wheel_viewport(app, pp.options_viewport(app), 2, delta=-120)
        except Exception as exc:
            say("ROWS %s %r failed: %s: %s" % (tab, group, type(exc).__name__, exc))
    # The 'Overhang speed' row paints ONE label over five inline fields
    # (#264 / #272). In runs 7f9beea4 and 50798c59 every op typed into the
    # SAME Edit (only overhang_3_4_speed changed, holding the last value):
    # the engine found one enabled Edit there, not five. Dump the row.
    try:
        ui.main_input()
        pp.click_tab(app, "Speed", "speed")
        ui.pause(1.0)
        pp.scroll_group_into_view(app, "Overhang")
        y = _find_phrase_row(app, "^Overhang speed", None)
        say("OVERHANG '^Overhang speed' label y=%r" % (y,))
        for view in range(3):
            words = pp.ocr_band(app, psm=3)
            lines = {}
            for t, x, yw, _ww, _hh in words:
                key = next((k for k in lines if abs(k - yw) <= 10), yw)
                lines.setdefault(key, []).append((x, t))
            say("OVERHANG view%d lines: %r" % (view, [
                "%d:%s" % (k, " ".join(t for _x, t in sorted(v))) for k, v in sorted(lines.items())]))
            for t, c, r, h, lx, ly in pp.kids(app):
                cy = (r[1] + r[3]) // 2
                if c in ("Edit", "Button", "ComboBox", "Static", "msctls_updown32") \
                        and u32.IsWindowVisible(h) and y - 24 <= cy <= y + 90 and lx < 424:
                    say("   %s %r rect=%r enabled=%s" % (
                        c, t[:16], r, bool(u32.IsWindowEnabled(h))))
            pp.wheel_viewport(app, pp.options_viewport(app), 2, delta=-120)
    except Exception as exc:
        say("OVERHANG probe failed: %s: %s" % (type(exc).__name__, exc))
    if shots:
        # One image with every popup that was opened (the harvest carries
        # exactly one probe picture: param_failure.png).
        try:
            from PIL import Image, ImageDraw
            width = max(im.shape[1] for _t, im in shots) + 20
            height = sum(im.shape[0] + 24 for _t, im in shots) + 10
            sheet = Image.new("RGB", (width, height), (40, 40, 40))
            draw = ImageDraw.Draw(sheet)
            top = 5
            for text, rgb in shots:
                draw.text((10, top), text[:70], fill=(255, 255, 0))
                top += 22
                sheet.paste(Image.fromarray(rgb), (10, top))
                top += rgb.shape[0] + 2
            sheet.save(ui.artifacts / "param_failure.png")
            say("popups sheet saved: %d popups, %dx%d" % (len(shots), width, height))
        except Exception as exc:
            say("popups sheet failed: %s: %s" % (type(exc).__name__, exc))
    if CENSUS_ROWS_ALL:
        # Every line of every page, top to bottom, two notches per step
        # (120px, a third of the visible band, so no row can be skipped).
        # This is the offline fixture the ops are checked against: the
        # source atlas is not the build, and queue20 spent 10+ minutes per
        # scenario on labels that a page of real text rules out at once.
        # Parse the 'ROWDUMP <tab> <view> <json>' lines of the worker log
        # with tools/rows_from_census.py.
        for tab, hint in hints.items():
            try:
                ui.main_input()
                pp.click_tab(app, tab, hint)
                ui.pause(1.0)
                last = None
                for view in range(90):
                    words = pp.ocr_band(app, psm=3)
                    lines = {}
                    for t, x, yw, _ww, _hh in words:
                        key = next((k for k in lines if abs(k - yw) <= 10), yw)
                        lines.setdefault(key, []).append((x, t))
                    row = ["%d:%s" % (k, " ".join(t for _x, t in sorted(v)))
                           for k, v in sorted(lines.items())]
                    say("ROWDUMP %s %d %s" % (tab, view, json.dumps(row, ensure_ascii=True)))
                    sig = tuple(r.split(":", 1)[1] for r in row)
                    if sig == last:
                        break
                    last = sig
                    pp.wheel_viewport(app, pp.options_viewport(app), 2, delta=-120)
            except Exception as exc:
                say("ROWDUMP %s failed: %s: %s" % (tab, type(exc).__name__, exc))
    if CENSUS_FULL:
        _census_pages_full(ui)
    raise ProtocolError("param_census_done")
