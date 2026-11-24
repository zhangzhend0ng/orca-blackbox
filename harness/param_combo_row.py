"""Row-anchored combo picking for painted parameter pages.

pp.set_combo_by_popup locates the combo by its painted VALUE, which is
ambiguous when sibling rows share a value (run 6d6fef17: two 'Monotonic'
pattern rows). This helper locates the combo by its painted ROW LABEL
(phrase OCR) and reuses the same popup capture/OCR/click mechanics."""
import re
import time

from .agent_protocol import ProtocolError
from .param_case_lib import _find_phrase_row


def pick_combo_at_label(ui, label, target, group_substr=None):
    """Open the combo on the row labeled `label` and click the popup row
    containing `target`; verify via the combo's real window text."""
    from . import process_panel as pp
    from harness import export_util, mix_dialog_util as mdu, winutil
    import numpy as np
    from win32gui import EnumChildWindows, IsWindowVisible

    wu, app = ui.wu, ui.app
    ui.main_input()
    if group_substr and not pp.scroll_group_into_view(app, group_substr):
        # a wrong group name must not degrade into a whole-page search for
        # the label (fa706g3 review D2, 2026-11-23)
        raise ProtocolError("param_combo_group:" + group_substr)

    def locate_combo():
        """((cx, cy), bounds) of the combo on the row labeled `label`, or None."""
        y_row = _find_phrase_row(app, label, group_substr=None)  # already scrolled
        if y_row is None:
            return None
        canvas_left = wu.window_rect(_canvas(ui))[0]
        origin_x, origin_y = wu.client_to_screen(app.hwnd, 0, 0)
        combo = []

        def collect(handle, _):
            if (wu.window_class(handle) != "ComboBox" or not IsWindowVisible(handle)
                    or wu._window_pid(handle) != app.pid):
                return True
            b = wu.window_rect(handle)
            cy = (b[1] + b[3]) // 2 - origin_y
            # On the matched line, or ~15px off it: a label that wraps to
            # two lines has its control centred on the ROW (fa706g3 review;
            # find_option_checkbox does the same for boxes).
            if (abs(cy - y_row) <= 14 or abs(abs(cy - y_row) - 15) <= 8) \
                    and 0 <= (b[0] + b[2]) // 2 < canvas_left:
                combo.append((handle, list(b)))
            return True

        EnumChildWindows(app.hwnd, collect, None)
        if len(combo) == 1:
            bounds = combo[0][1]
        elif len(combo) == 0:
            # Painted-value combos carry no ComboBox HWND (runs 5e095f2c/
            # 79ca1e8c): the value zone at the row's right opens the popup.
            # The value is its own small window (census f1c5433b: 120x26
            # 'Auto'): take that window's centre when the point resolves to
            # one. WindowFromPoint hands back the big row container for a
            # DISABLED value - that is left to the open attempt to report.
            best = None
            for dy in (0, 15, -15):
                target = winutil.window_from_screen_point(canvas_left - 90, y_row + dy + origin_y)
                rect = winutil.window_rect(target) if target else None
                if rect and (rect[2] - rect[0]) <= 250 and (rect[3] - rect[1]) <= 60:
                    best = rect
                    break
            bounds = best or (canvas_left - 150, y_row + origin_y - 13,
                              canvas_left - 30, y_row + origin_y + 13)
        else:
            raise ProtocolError("param_combo_field:" + label + ":" + str(len(combo)))
        return ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2), bounds

    found = locate_combo()
    if not found:
        raise ProtocolError("param_combo_row:" + label)
    (cx, cy), _bounds = found
    # Park the row before the popup is opened: its list opens straight down
    # and a row that lands under the taskbar cannot be clicked (brim run
    # f323be97 OCR'd an empty popup, by_object clicked Shell_TrayWnd).
    if pp.park_for_popup(app, _bounds):
        found = locate_combo()  # the row moved up with the page
        if not found:
            raise ProtocolError("param_combo_row_after_park:" + label)
        (cx, cy), _bounds = found

    def _click_point(point, pr, ph, what):
        """True = clicked, 'offscreen' = the row is under the taskbar."""
        x, y = pr[0] + point[0], pr[1] + point[1]
        if not pp.popup_hit_clickable(ph, x, y):
            print("[popup] row %r at (%d,%d) is off-screen (popup %r, "
                  "work area %r)" % (what, x, y, pr, pp.work_area()), flush=True)
            return "offscreen"
        print("[popup] clicking %r at (%d,%d) in popup %r; rows OCR'd: %r" % (
            what, x, y, pr, [(t, x_, y_) for t, x_, y_, *_ in words][:16]), flush=True)
        winutil.msg_click_screen(x, y)
        return True

    def _click_target(words_, pr, ph):
        """True = clicked, 'offscreen' = the row is under the taskbar,
        False = no such row in these words. Line-level match: a two-word
        target is never inside one OCR word."""
        for cx_, cy_, _line in pp.popup_line_hits(words_, target):
            hit = _click_point((cx_, cy_), pr, ph, target)
            if hit is True or hit == "offscreen":
                return hit
        print("[popup] %r not among the popup rows: %r" % (
            target, [(t, x_, y_) for t, x_, y_, *_ in words_][:16]), flush=True)
        return False

    def _popup_words(ph):
        # psm 6 (uniform block): the default psm 3 dropped whole rows of
        # list-like popups - '1 PETG' and '5 PLA' of the extruder list were
        # missing while '2) PLA' / '4 PLA' came through (census c814315c).
        time.sleep(0.8)
        words_ = []
        for _attempt in range(3):
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words_ = mdu.ocr_words_img(img, scale=3, psm=6)
            if words_:
                break
            time.sleep(0.6)
        return words_

    clicked = False
    offscreen = False
    words = []
    for attempt in (1, 2):
        popup = None
        print("[popup] row %r: opening the combo at (%d,%d) attempt %d" % (
            label, cx, cy, attempt), flush=True)
        for click in (1, 2):   # a just-dismissed popup can swallow a click
            winutil.msg_click_screen(cx, cy, app.hwnd)
            for _ in range(12 if click == 1 else 20):
                popup = export_util.wait_popup(app.pid, timeout_s=0.5)
                if popup:
                    break
            if popup:
                break
            time.sleep(0.6)
        if not popup:
            raise ProtocolError("param_combo_popup:" + label)
        pr, ph = popup[2], popup[3]
        print("[popup] opened %r" % (pr,), flush=True)
        words = _popup_words(ph)
        first = _click_target(words, pr, ph)
        if first is False:
            # '1 PLA' cannot be read as text on an all-PLA fixture
            # (extruder_row_point): take the entry by its number instead.
            point = extruder_row_point(words, pr, target)
            if point is not None:
                print("[popup] %r read by position in popup %r; lines OCR'd: %r; entry point %r" % (
                    target, pr, _popup_lines(words), point), flush=True)
                first = _click_point(point, pr, ph, target)
        if first is True:
            clicked = True
            break
        if first == "offscreen":
            offscreen = True
            if attempt == 2:
                break
            # close it, move the page further up, open it again - once
            pp.close_popup(app, ph, (cx, cy))
            vp = pp.options_viewport(app)
            if vp:
                pp.wheel_viewport(app, vp, 3, delta=-120)
            found = locate_combo()
            if not found:
                raise ProtocolError("param_combo_row_after_park:" + label)
            (cx, cy), _bounds = found
            continue
        break
    if offscreen and not clicked:
        # wheeling a popup whose rows are under the taskbar cannot help
        raise ProtocolError("param_combo_popup_offscreen:" + target + ":" + repr(pr))
    for page in range(8):
        if clicked:
            break
        # 2026-11-22 fa706g3 hands-on diagnosis (fa706g3-gui-diag-2026-11-22):
        # the popup is a childless self-drawn list. WM_CHAR typeahead never
        # renders, and ANY key (VK_NEXT / VK_DOWN, real or posted) CLOSES it.
        # The proven deep-item recipe is a REAL wheel, ONE notch per step
        # with >=0.4s settle (Gyroid fully visible after 2 notches, list
        # freezes after ~4), with the touch-style painted bar as fallback
        # (drag UP = content follows finger deeper) where the wheel does
        # not accumulate at all (VM 2.4.0 rebound records).
        from win32gui import EnumChildWindows
        if page == 0:
            kids = []

            def census(handle, _):
                kids.append((handle, wu.window_class(handle)))
                return True

            EnumChildWindows(ph, census, None)
            print("[popup] children: " + repr(kids)[:300], flush=True)
        pcx, pcy = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
        winutil.real_wheel_screen(pcx, pcy, -1)
        time.sleep(0.45)
        w, hgt, bgra = winutil.capture_window(ph)
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        words = mdu.ocr_words_img(img, scale=3, psm=6)
        if _click_target(words, pr, ph) is True:
            clicked = True
        if clicked:
            break
        if page == 1:
            # Wheel not accumulating on this build: pull the touch-style
            # bar (right edge, drag UP drags deep items into view).
            winutil.real_drag_screen(pr[2] - 6, pcy + (pr[3] - pr[1]) // 4,
                                     pr[2] - 6, pcy - (pr[3] - pr[1]) // 4)
            time.sleep(0.6)
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3, psm=6)
    if not clicked:
        raise ProtocolError("param_combo_target:" + target + ":" +
                            "|".join(t for t, *_ in words)[:80])
    time.sleep(2.5)  # a combo commit rebuilds the page
    ui.main_input()
    # Readback (r4.2). This function used to return after its click with no
    # postcondition at all: fa run f4b87b67 logged nothing, reported success
    # and left the row painting 'Fuzzy skin ~ None'. The row's CONTROL must
    # show the target now, read on the line that was clicked.
    value, line = _row_value(ui, label, anchor=(cx, cy))
    print("[popup] row %r now paints value %r, line %r (wanted %r)" % (
        label, value, line, target), flush=True)
    if not _shows(value, target):
        raise ProtocolError("param_combo_readback:" + target + ":" +
                            (value or line)[:60])


def _popup_lines(words):
    """[(cy, text)] of a popup capture: the OCR words grouped into lines by y
    (10 px), each line's text left to right, the lines top to bottom."""
    rows = []
    for t, x, y, _w, h in sorted(words, key=lambda word: word[2]):
        for row in rows:
            if abs(row[0] - y) <= 10:
                row[1].append((x, y + h // 2, t))
                break
        else:
            rows.append([y, [(x, y + h // 2, t)]])
    lines = []
    for _y, parts in rows:
        parts.sort()
        lines.append((sum(cy for _x, cy, _t in parts) // len(parts),
                      " ".join(t for _x, _cy, t in parts)))
    lines.sort()
    return lines


def extruder_row_point(words, popup_rect, target):
    """Point (x, y) inside `popup_rect` (left, top, right, bottom) of entry
    number N of an extruder popup, for a target spelled '<N> <type>' ('1 PLA');
    None when the OCR words do not sit on such a list.

    Why by position: a fixture whose filaments are all PLA paints the rows
    'Default', '1 PLA' .. '5 PLA', and OCR drops or mangles the leading digit
    (run 1f8a4309, popup 180 px high: '~ Default' y8, '2) PLA' y65, 'By PLA'
    y95, '4 PLA' y129, 'PLA' y159 - the '1 PLA' row itself was not read), so
    '1 PLA' cannot be matched as text (param_combo_target). The list is a
    grid: every row is popup height / row count high and the first row starts
    at the top. The row count is read off the rows OCR did read - their
    spacing must be one pitch or a whole multiple of it, the first row must
    read 'Default' and every other row must end with the target's type word.
    A wrong pick cannot pass silently: the pilot checks the number that lands
    in the saved project."""
    found = re.match(r"^(\d+)\s+([A-Za-z]+)$", target.strip())
    if not found:
        return None
    index, kind = int(found.group(1)), found.group(2).lower()
    lines = _popup_lines(words)
    if len(lines) < 3 or lines[0][1].lower().split()[-1:] != ["default"]:
        return None
    tops = [cy for cy, _text in lines]
    gaps = [b - a for a, b in zip(tops, tops[1:])]
    pitch = min(gaps)
    if pitch < 18 or any(abs(gap - pitch * max(1, round(gap / pitch))) > 6 for gap in gaps):
        return None
    left, top, right, bottom = popup_rect
    count = int(round((bottom - top) / pitch))
    if count < 2 or abs(count * pitch - (bottom - top)) > pitch / 2:
        return None
    pitch = (bottom - top) / count
    seats = {}
    for cy, text in lines:
        seat = int(round((cy - tops[0]) / pitch))
        if seat >= count or abs((cy - tops[0]) / pitch - seat) > 0.25:
            return None
        if seat and (seat in seats or text.lower().split()[-1:] != [kind]):
            return None
        seats[seat] = text
    # the pitch is anchored by at least two rows after 'Default', and the entry
    # taken sits at or before the last row OCR saw - never extrapolated past it
    if len([seat for seat in seats if seat]) < 2 or index > max(seats):
        return None
    if not 1 <= index < count:
        return None
    # whole pixels: the click helpers take ints (fa706g3 run a876d8b8 died on
    # a float here, 2026-11-24)
    return ((left + right) // 2 - left, int((index + 0.5) * pitch))


def _shows(value, target):
    """True when one reading of `value` is exactly the words of `target`
    (readings are joined with ' | '). Not a substring test: 'Rib' is inside
    'Rectangle', and three of the twelve rowcombo targets are the first word
    of another entry of their own popup ('Rectilinear Interlaced',
    'Aligned Rectilinear') - a substring readback passes the wrong pick
    (fa review of 36cbb8c). Digits and signs are ignored: '1 PETG' is PETG."""
    want = re.findall(r"[a-z]+", target.lower())
    for reading in value.split(" | "):
        words = [w for w in re.findall(r"[a-z]+", reading.lower()) if len(w) >= 2]
        if words == want:
            return True
    return False


def _line_names(line, label):
    """True when the OCR line on the anchor carries the row's label - or is
    empty: a just-changed row drops out of the band OCR (fa run e9071eba),
    which is exactly when the anchor is needed. A non-empty line WITHOUT
    the label means the page moved under the anchor and the reading belongs
    to another row (fa review). OCR swaps I/l and drops endings, so a label
    word counts as seen when some line word starts with its first three
    letters."""
    words = re.findall(r"[a-z]+", line.lower())
    if not words:
        return True
    return any(any(w.startswith(part[:3]) for w in words)
               for part in re.findall(r"[a-z]+", label.lstrip("^").lower()) if len(part) >= 3)


def _row_value(ui, label, anchor=None):
    """(value, line) the row labeled `label` shows where it is now.

    `anchor` is the screen point the combo was clicked at. The page
    rebuilds around the row but the row stays under that point, and the
    phrase scan cannot be trusted right after a commit: a just-changed row
    paints its label orange inside a teal focus border and tesseract
    dropped the whole line (fa run e9071eba: 'Fuzzy skin' resolved to the
    next row, 'Fuzzy skin generator mode ~ Displacement'). So the anchor
    line is read first and the phrase scan is the fallback.

    `value` is what the row's CONTROL shows, read three ways and joined with
    ' | ': the text of its value window, the OCR of the value zone and the
    OCR of that zone cut past a colour swatch. `line` is the OCR of the whole
    label line - it goes into the log, not into the verdict: a target like
    'on' is inside 'ironing'. ('', '') when the row is gone.

    One reading does not cover this page (fa run 4ec54abd, measured on its
    failure screenshot): the extruder combo paints a colour swatch and the
    OCR of its zone returns nothing, while the zone cut at the swatch reads
    'PETG' - and that cut garbles a plain value ('Yefault')."""
    from . import process_panel as pp
    app = ui.app
    try:
        ox, oy = pp.client_origin(app)
        anchored = ("", "")
        if anchor is not None:
            anchored = _read_row(ui, anchor[1] - oy, ox, oy)
            if anchored[0] and _line_names(anchored[1], label):
                return anchored
        y = _find_phrase_row(app, label, group_substr=None)
        if y is None or (anchor is not None and y == anchor[1] - oy):
            # nothing better than the anchor: its reading goes back unchecked
            return anchored
        return _read_row(ui, y, ox, oy)
    except Exception as exc:  # diagnostic path: never mask the real failure
        print("[popup] row value not read: %s: %s" % (type(exc).__name__, exc), flush=True)
        return "", ""


def _read_row(ui, y, ox, oy):
    """(value, line) painted on the client line y: see _row_value."""
    from . import process_panel as pp
    from harness import mix_dialog_util as mdu
    app = ui.app
    boxes, texts = [], []
    for t, c, r, h, lx, ly in pp.kids(app):
        if not t.strip() or c == "panel" or not pp.user32.IsWindowVisible(h):
            continue
        if not (pp.VALUE_X0 - 10 <= lx < pp.SB_W and r[2] - r[0] <= 320):
            continue
        # centre within 10 px of the line and no taller than a value window
        # (26 px): at the old +/-14 the boxes of a 27 px stack could both
        # land in one reading (fa review)
        if abs((r[1] + r[3]) // 2 - (y + oy)) <= 10 and (r[3] - r[1]) <= 30:
            boxes.append(r)
            texts.append(t.strip())
    img = pp.capture_bgr(app)
    height = img.shape[0]
    if boxes:                   # client rect of the value control(s)
        x0 = min(b[0] for b in boxes) - ox
        x1 = max(b[2] for b in boxes) - ox
        top = min(b[1] for b in boxes) - oy
        bot = max(b[3] for b in boxes) - oy
    else:                       # no value window: the standard value zone
        x0, x1, top, bot = 246, 366, y - 12, y + 12

    def read(x_a, y_a, x_b, y_b):
        """OCR of the client rect (x_a, y_a)-(x_b, y_b) as one line."""
        crop = img[max(0, y_a):min(height, y_b), max(0, x_a):min(x_b, img.shape[1])]
        if crop.size == 0:
            return ""
        return " ".join(t for t, *_ in mdu.ocr_words_img(crop, scale=3, psm=6))

    readings = [" ".join(texts),
                read(x0 - 10, top - 5, x1 + 10, bot + 5),
                read(x0 + 26, top + 3, x1 - 4, bot - 3)]
    vp = pp.options_viewport(app)
    band_top = max(0, vp[0][1] - oy) if vp else 0
    band_bot = min(height, vp[0][3] - oy) if vp else height
    words = mdu.ocr_words_img(img[band_top:band_bot, :pp.SB_W], scale=3, psm=6)
    line = " ".join(t for t, _x, yy, _w, hgt in words
                    if abs(yy + hgt // 2 + band_top - y) <= 14)
    return " | ".join(r for r in readings if r), line


def _canvas(ui):
    from .param_case_lib import _canvas_hwnd
    return _canvas_hwnd(ui)
