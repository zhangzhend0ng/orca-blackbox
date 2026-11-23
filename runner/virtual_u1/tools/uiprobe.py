"""uiprobe.py — read what the CLI web UI renders, straight from its semantics
tree. The device control page paints to canvas, but Flutter mirrors every
labelled widget into the semantics tree as text drawn from the same widget
state — so this is the rendered content, not a model guess.

Two surfaces matter for monitoring (locale en-US):

  Control panel   two temperature buttons, text "<current>\\n/\\n<target>\\n°C"
                  (nozzle above bed; integers — 210.5 renders as 210)
  Printing Task   one group whose aria-label joins the card's labels with
                  "\\n": "|", then filename / "<n>%" / "<cur>/<tot> layer" /
                  "Time remaining：<t>" (each only when available), then the
                  state badge and the device name.

    nodes = Page(9224).semantics()
    task_card(nodes)      -> {"state", "device", "filename", "percent", ...}
    temperatures(nodes)   -> {"nozzle": (current, target), "bed": (...)}
    texts(nodes)          -> every string on the page (for ad-hoc checks)
    exception_dialog(nodes) / offline_dialog(nodes) -> {"rect", "full"} or None
    ocr_words(png)        -> words the Windows OCR engine reads off a screenshot
    bar_fill(png)         -> filled fraction of the card's progress bar (pixels)
"""
import re

TASK_HEADER = "Printing Task"
TEMP_RE = re.compile(r"(-?\d+)\n/\n(-?\d+)\n°C")
PERCENT_RE = re.compile(r"(\d+)%")
LAYER_RE = re.compile(r"(.+?) layer")
REMAINING_RE = re.compile(r"Time remaining[：:](.*)")


def task_group(nodes):
    """The Printing Task card's semantics group, or None when the page has no
    card (offline placeholder keeps the header but drops the group label)."""
    return next((n for n in nodes if n["role"] == "group" and n["label"].startswith("|\n")
                 and TASK_HEADER in n["full"]), None)


def task_card(nodes):
    """Parsed Printing Task card; keys for the optional lines exist only when
    the card shows them (idle card = state + device only). The card is the
    group whose subtree carries the header text — which element of the subtree
    holds it as its own text shifts between rebuilds, so match on the full
    subtree text, not on `text`."""
    grp = task_group(nodes)
    if grp is None:
        raise LookupError("Printing Task card not on page")
    card = {"label": grp["label"]}
    rest = []
    for line in grp["label"].split("\n"):
        if not line or line == "|":
            continue
        m = PERCENT_RE.fullmatch(line)
        if m:
            card["percent"] = int(m.group(1))
            continue
        m = LAYER_RE.fullmatch(line)
        if m:
            card["layer"] = m.group(1)
            continue
        m = REMAINING_RE.fullmatch(line)
        if m:
            card["remaining"] = m.group(1)
            continue
        rest.append(line)
    if len(rest) < 2:
        raise LookupError("task card label has no state/device pair: %r" % grp["label"])
    card["state"], card["device"] = rest[-2], rest[-1]
    card["details"] = rest[:-2]          # file name, or fault text on an error card
    return card


def temperatures(nodes):
    found = []
    for n in nodes:
        if n["role"] != "button":
            continue
        m = TEMP_RE.fullmatch(n["text"])
        if m:
            found.append((n["rect"][1], int(m.group(1)), int(m.group(2))))
    if len(found) < 2:
        raise LookupError("temperature buttons not found: %r" % (found,))
    found.sort()                          # nozzle row sits above bed row
    return {"nozzle": (found[0][1], found[0][2]), "bed": (found[1][1], found[1][2])}


def texts(nodes):
    """Every distinct string on the page: own texts plus label lines."""
    out = []
    for n in nodes:
        for s in [n["text"]] + n["label"].split("\n"):
            s = s.strip()
            if s and s != "|" and s not in out:
                out.append(s)
    return out


OFFLINE_TEXT = "processing the offline state"
MODAL_BUTTONS = ("ok", "got it")


def modal(nodes):
    """Whatever modal is up -> {"kind", "rect", "full"}, else None. Every
    modal on this page closes with an OK / Got it button that nothing else on
    the page uses; the modal's content is the smallest group around it.
    kind: exception | offline | authorization | other. Detect by button, not
    by text — a kind not seen yet must still count as "a modal is up"."""
    btn = next((n for n in nodes if n["role"] == "button" and n["text"].lower() in MODAL_BUTTONS), None)
    if btn is None:
        return None
    bx, by = btn["rect"][0] + btn["rect"][2] / 2, btn["rect"][1] + btn["rect"][3] / 2
    groups = [n for n in nodes if n["role"] == "group"
              and n["rect"][0] <= bx <= n["rect"][0] + n["rect"][2]
              and n["rect"][1] <= by <= n["rect"][1] + n["rect"][3]]
    grp = min(groups, key=lambda n: n["rect"][2] * n["rect"][3]) if groups else btn
    full = grp["full"]
    if "Error Code:" in full:
        kind = "exception"
    elif OFFLINE_TEXT in full:
        kind = "offline"
    elif "authorization" in full.lower():
        kind = "authorization"
    else:
        kind = "other"
    return {"kind": kind, "rect": grp["rect"], "full": full}


def exception_dialog(nodes):
    """The modal raised on notify_exception_notification; its texts are
    concatenated in `full` and the error-code value is painted without
    semantics — read that with ocr_words() on `rect`."""
    m = modal(nodes)
    return m if m and m["kind"] == "exception" else None


def offline_dialog(nodes):
    """The modal shown when the device link drops. It closes by itself once
    the device reconnects."""
    m = modal(nodes)
    return m if m and m["kind"] == "offline" else None


def find_button(nodes, text):
    """Semantics id of the first button whose own text matches (case-insensitive), else None."""
    for n in nodes:
        if n["role"] == "button" and n["text"].lower() == text.lower():
            return int(n["id"].rsplit("-", 1)[1])
    return None


def temps_rect(nodes):
    """Clip around both temperature buttons, for a screenshot/OCR of them."""
    rects = [n["rect"] for n in nodes if n["role"] == "button" and TEMP_RE.fullmatch(n["text"])]
    if len(rects) < 2:
        raise LookupError("temperature buttons not on page")
    x = min(r[0] for r in rects) - 8
    y = min(r[1] for r in rects) - 6
    return (x, y, max(r[0] + r[2] for r in rects) - x + 16, max(r[1] + r[3] for r in rects) - y + 12)


def bar_fill(png, min_width=300):
    """Fraction of the task card's progress bar that is filled (blue), from a
    screenshot of the card's lower part; None when no bar is painted there.
    The bar is the widest horizontal run of blue fill / light-grey track; its
    widest (middle) row gives the ratio without the rounded caps."""
    import pngpix
    rows = pngpix.decode(png)
    w = len(rows[0]) // 3
    best = None
    for row in rows:
        x = 0
        while x < w:
            r, g, b = row[x * 3:x * 3 + 3]
            blue = b > 150 and b > r + 60 and b > g + 20
            track = 190 <= r <= 245 and 190 <= g <= 245 and 190 <= b <= 245 and abs(r - b) < 25
            if blue or track:
                x0, nblue = x, 0
                while x < w:
                    r, g, b = row[x * 3:x * 3 + 3]
                    if not (b > 150 and b > r + 60 and b > g + 20
                            or 190 <= r <= 245 and 190 <= g <= 245 and 190 <= b <= 245 and abs(r - b) < 25):
                        break
                    nblue += b > 150 and b > r + 60 and b > g + 20
                    x += 1
                if x - x0 >= min_width and (best is None or x - x0 > best[0]):
                    best = (x - x0, nblue)
            else:
                x += 1
    return None if best is None else best[1] / best[0]


def ocr_words(png):
    """[(word, x, y, w, h)] read by the Windows OCR engine (tools/ocr_words.ps1)
    from PNG bytes. Capture at scale 2 — small canvas text is illegible at 1x."""
    import os
    import subprocess
    import tempfile
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_words.ps1")
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(png)
        raw = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Path", path],
                             capture_output=True, timeout=90).stdout
    finally:
        os.remove(path)
    try:
        out = raw.decode("utf-8")
    except UnicodeDecodeError:
        out = raw.decode("mbcs", "replace")
    words = []
    for tok in out.split():
        m = re.fullmatch(r"(.+)@(-?\d+),(-?\d+),(\d+)x(\d+)", tok)
        if m:
            words.append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    return words
