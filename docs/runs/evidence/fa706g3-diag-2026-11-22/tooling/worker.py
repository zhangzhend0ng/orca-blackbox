# -*- coding: utf-8 -*-
"""fa706g3 session-1 GUI worker.

Runs INSIDE the interactive console session (started via the zcode_gui_task
scheduled task) and executes commands from C:\\coil\\fa706_diag\\cmd.json with
REAL SendInput mouse/keyboard plus winutil captures, writing result_<id>.json
and PNG shots into out\\ so the session-0 agent (which has vision on files)
can drive the interactive desktop remotely.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

BASE = Path(r"C:\coil\fa706_diag")
OUT = BASE / "out"
CMD = BASE / "cmd.json"
STOP = BASE / "stop"
REPO = Path(r"C:\coil\orca-blackbox-v3-r1")
sys.path.insert(0, str(REPO))
os.environ["ORCA_BB_ALLOW_HOST"] = "1"  # host work explicitly ordered by control
os.environ["PATH"] = r"C:\Program Files\Tesseract-OCR;" + os.environ["PATH"]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import harness.winutil as wu  # noqa: E402

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
OUT.mkdir(parents=True, exist_ok=True)

wu.make_dpi_aware()

# ---------------------------------------------------------------- real input
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120
VK_MAP = {"DOWN": 0x28, "UP": 0x26, "END": 0x23, "HOME": 0x24, "PRIOR": 0x21,
          "NEXT": 0x22, "LEFT": 0x25, "RIGHT": 0x27, "RETURN": 0x0D,
          "ESCAPE": 0x1B, "SPACE": 0x20, "TAB": 0x09, "BACK": 0x08,
          "SHIFT": 0x10, "CONTROL": 0x11, "MENU": 0x12, "DELETE": 0x2E}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _U)]


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    n = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if n != len(inputs):
        raise RuntimeError("SendInput incomplete: %d/%d" % (n, len(inputs)))


def _key_input(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(vk, scan, flags, 0, None)
    return inp


def key_action(vk, mode="tap", times=1, interval_ms=60):
    for _ in range(times):
        if mode in ("tap", "down"):
            _send(_key_input(vk=vk))
        if mode in ("tap", "up"):
            time.sleep(0.02)
            _send(_key_input(vk=vk, flags=KEYEVENTF_KEYUP))
        if times > 1:
            time.sleep(interval_ms / 1000.0)


def text_action(chars, interval_ms=25):
    for ch in chars:
        _send(_key_input(scan=ord(ch), flags=KEYEVENTF_UNICODE))
        time.sleep(0.01)
        _send(_key_input(scan=ord(ch),
                         flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        time.sleep(interval_ms / 1000.0)


def _mouse_input(flags, data=0):
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(0, 0, data, flags, 0, None)
    return inp


def move_to(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.03)


def click_action(x, y, button="left", count=1, interval_ms=140):
    dn = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
    for _ in range(count):
        move_to(x, y)
        _send(_mouse_input(dn))
        time.sleep(0.06)
        _send(_mouse_input(up))
        if count > 1:
            time.sleep(interval_ms / 1000.0)
    time.sleep(0.05)


def drag_action(x0, y0, x1, y1, steps=40, dur_ms=500, button="left"):
    dn = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
    move_to(x0, y0)
    time.sleep(0.15)
    _send(_mouse_input(dn))
    step_s = dur_ms / 1000.0 / max(1, steps)
    for i in range(1, steps + 1):
        move_to(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(step_s)
    time.sleep(0.25)
    _send(_mouse_input(up))
    time.sleep(0.1)


def wheel_action(notches, x=None, y=None, settle_ms=None):
    if x is not None and y is not None:
        move_to(x, y)
    data = int(notches) * WHEEL_DELTA
    # negative mouseData = wheel down (toward user) per SendInput semantics
    _send(_mouse_input(MOUSEEVENTF_WHEEL, data & 0xFFFFFFFF))
    if settle_ms:
        time.sleep(settle_ms / 1000.0)


# ------------------------------------------------------------------ capture
def _png_from_bgra(w, h, bgra, path, rect=None, scale=1):
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)
    if rect:
        x0, y0, x1, y1 = rect
        img = img[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    if scale != 1:
        img = np.kron(img[:, :, :3], np.ones((scale, scale, 1))).astype(np.uint8)
    else:
        img = img[:, :, :3]
    Image.fromarray(img[:, :, ::-1].copy(), "RGB").save(path)  # BGR->RGB
    return str(path), img.shape[1], img.shape[0]


def shot(name, hwnd=None, rect=None, scale=1):
    path = OUT / (name + ".png")
    if hwnd:
        w, h, bgra = wu.capture_window(int(hwnd))
    else:
        w, h, bgra = wu.screen_grab()
    p, pw, ph = _png_from_bgra(w, h, bgra, path, rect, scale)
    return {"path": p, "w": pw, "h": ph, "src_w": w, "src_h": h}


def ocr_words(name, hwnd=None, rect=None, psm=6, scale=3):
    import pytesseract
    if hwnd:
        w, h, bgra = wu.capture_window(int(hwnd))
    else:
        w, h, bgra = wu.screen_grab()
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    if rect:
        x0, y0, x1, y1 = rect
        img = img[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
    big = np.kron(img, np.ones((scale, scale, 1))).astype(np.uint8)
    data = pytesseract.image_to_data(
        big, config="-l eng --psm %d" % psm, output_type=pytesseract.Output.DICT)
    ox = rect[0] if rect else 0
    oy = rect[1] if rect else 0
    words = []
    for i, t in enumerate(data["text"]):
        t = t.strip()
        if not t or int(float(data["conf"][i])) <= 40:
            continue
        words.append([t, data["left"][i] // scale + ox,
                      data["top"][i] // scale + oy,
                      data["width"][i] // scale, data["height"][i] // scale,
                      int(float(data["conf"][i]))])
    return words


# -------------------------------------------------------------------- misc
def enum_windows_action(title_sub=None, pid=None):
    res = []
    for hwnd, wpid in wu.enum_windows():
        if not user32.IsWindowVisible(hwnd):
            continue
        if pid and wpid != pid:
            continue
        title = wu.window_title(hwnd)
        if title_sub and title_sub.lower() not in title.lower():
            continue
        res.append({"hwnd": hwnd, "class": wu.window_class(hwnd),
                    "title": title, "rect": list(wu.window_rect(hwnd)),
                    "pid": wpid})
    return res


def children_action(hwnd, deep=False):
    res = []

    def collect(handle):
        res.append({"hwnd": handle, "class": wu.window_class(handle),
                    "rect": list(wu.window_rect(handle)),
                    "visible": bool(user32.IsWindowVisible(handle))})
        return True
    EnumChildWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                              ctypes.c_void_p)

    @EnumChildWindowsProc
    def cb(handle, _):
        return collect(handle)
    user32.EnumChildWindows(int(hwnd), cb, 0)
    return res


STATE = {"app": None, "pid": None, "main_hwnd": None, "popup": None,
         "popup_rect": None}


def find_popup_action(pid=None):
    pid = pid or STATE["pid"]
    best = None
    for hwnd, wpid in wu.enum_windows():
        if pid and wpid != pid:
            continue
        if not user32.IsWindowVisible(hwnd):
            continue
        if wu.window_class(hwnd) == "wxWindowNR" \
                and wu.window_title(hwnd).strip() == "panel" \
                and hwnd != STATE.get("main_hwnd"):
            best = hwnd  # keep last; normally exactly one
    STATE["popup"] = best
    STATE["popup_rect"] = list(wu.window_rect(best)) if best else None
    return {"popup": best, "rect": STATE["popup_rect"]}


def open_popup_action(x, y, tries=3):
    """Click the combo value zone; wait for the popup to exist. If the
    popup is already up, the click toggles it closed, so only re-click
    while no popup exists. Sets STATE.popup/rect."""
    for attempt in range(tries):
        click_action(x, y)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            find_popup_action()
            if STATE["popup"]:
                time.sleep(0.5)  # first paint settle
                return {"popup": STATE["popup"], "rect": STATE["popup_rect"],
                        "attempt": attempt + 1}
            time.sleep(0.3)
    return {"popup": None, "rect": None, "attempt": tries}


def _resolve_hwnd(step):
    h = step.get("hwnd")
    if h in ("popup", -1):
        if not STATE["popup"]:
            raise RuntimeError("no popup located (run findpopup first)")
        return STATE["popup"]
    return h


def launch_action(exe, datadir, model=None):
    args = [str(exe), "--datadir", str(datadir)]
    if model:
        args.append(str(model))
    popen = subprocess.Popen(args)
    STATE["app"] = popen
    STATE["pid"] = popen.pid
    hwnd = wu.find_main_window(popen.pid, timeout_s=90, stable_s=1.0)
    STATE["main_hwnd"] = hwnd
    wu.force_set_foreground(hwnd)
    return {"pid": popen.pid, "main_hwnd": hwnd,
            "rect": list(wu.window_rect(hwnd))}


BLOCKER_TITLES = {"update", "new version", "release notes"}


def sweep_action(pid=None, main_hwnd=None, budget_s=20.0):
    pid = pid or STATE.get("pid")
    main_hwnd = main_hwnd or STATE.get("main_hwnd")
    dismissed = []
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        for hwnd, wpid in wu.enum_windows():
            if (pid and wpid != pid) or hwnd == main_hwnd:
                continue
            title = wu.window_title(hwnd).strip().lower()
            if (title in BLOCKER_TITLES or "wizard" in title
                    or "update" in title or "new version" in title):
                wu.close_window(hwnd)
                dismissed.append(title)
                time.sleep(2.0)
        time.sleep(0.5)
    return {"dismissed": dismissed}


# ---------------------------------------------------------------- dispatch
def run_step(step, idx):
    act = step.get("action")
    extra = {}
    if act == "ping":
        extra["pong"] = True
    elif act == "sleep":
        time.sleep(step["ms"] / 1000.0)
    elif act == "launch":
        extra = launch_action(step["exe"], step["datadir"], step.get("model"))
    elif act == "sweep":
        extra = sweep_action(step.get("pid"), step.get("main_hwnd"),
                             step.get("budget_s", 20.0))
    elif act == "shot":
        extra = shot(step["name"], _resolve_hwnd(step), step.get("rect"),
                     step.get("scale", 1))
    elif act == "ocr":
        extra = {"words": ocr_words(step["name"], _resolve_hwnd(step),
                                    step.get("rect"), step.get("psm", 6),
                                    step.get("scale", 3))}
    elif act == "click":
        click_action(step["x"], step["y"], step.get("button", "left"),
                     step.get("count", 1), step.get("interval_ms", 140))
    elif act == "move":
        move_to(step["x"], step["y"])
    elif act == "findpopup":
        extra = find_popup_action(step.get("pid"))
    elif act == "openpopup":
        extra = open_popup_action(step["x"], step["y"], step.get("tries", 3))
        if not extra["popup"]:
            raise RuntimeError("openpopup failed")
    elif act == "wtext":
        h = _resolve_hwnd(step)
        extra = {"text": wu.window_title(int(h))}
    elif act == "mdown":
        move_to(step["x"], step["y"])
        time.sleep(0.1)
        _send(_mouse_input(MOUSEEVENTF_LEFTDOWN
                           if step.get("button", "left") == "left"
                           else MOUSEEVENTF_RIGHTDOWN))
    elif act == "mup":
        move_to(step["x"], step["y"])
        _send(_mouse_input(MOUSEEVENTF_LEFTUP
                           if step.get("button", "left") == "left"
                           else MOUSEEVENTF_RIGHTUP))
        time.sleep(0.1)
    elif act == "drag":
        drag_action(step["x0"], step["y0"], step["x1"], step["y1"],
                    step.get("steps", 40), step.get("dur_ms", 500),
                    step.get("button", "left"))
    elif act == "wheel":
        x, y = step.get("x"), step.get("y")
        if step.get("rel_popup") and STATE["popup_rect"]:
            x = STATE["popup_rect"][0] + (x if x is not None else 0)
            y = STATE["popup_rect"][1] + (y if y is not None else 0)
        wheel_action(step["notches"], x, y, step.get("settle_ms"))
    elif act == "key":
        vk = step.get("vk", VK_MAP.get(step.get("name", "").upper(), 0))
        key_action(vk, step.get("mode", "tap"), step.get("times", 1),
                   step.get("interval_ms", 60))
    elif act == "text":
        text_action(step["chars"], step.get("interval_ms", 25))
    elif act == "enum":
        extra = {"windows": enum_windows_action(step.get("title_sub"),
                                                step.get("pid"))}
    elif act == "children":
        extra = {"children": children_action(step["hwnd"])}
    elif act == "fg":
        extra = {"ok": wu.force_set_foreground(int(step["hwnd"]))}
    elif act == "fgmain":
        if not STATE.get("main_hwnd"):
            raise RuntimeError("no main hwnd in STATE")
        extra = {"ok": wu.force_set_foreground(STATE["main_hwnd"])}
    elif act == "max":
        h = step.get("hwnd")
        if h in ("main", 0, None):
            h = STATE.get("main_hwnd")
        user32.ShowWindow(int(h), 3)  # SW_MAXIMIZE
        time.sleep(0.6)
        extra = {"rect": list(wu.window_rect(int(h)))}
    elif act == "c2s":
        h = step.get("hwnd") or STATE.get("main_hwnd")
        if not h:
            raise RuntimeError("no hwnd for c2s")
        extra = {"screen": list(wu.client_to_screen(int(h), int(step["x"]),
                                                    int(step["y"])))}
    elif act == "clickclient":
        h = step.get("hwnd") or STATE.get("main_hwnd")
        if not h:
            raise RuntimeError("no hwnd for clickclient")
        sx, sy = wu.client_to_screen(int(h), int(step["x"]), int(step["y"]))
        click_action(sx, sy, step.get("button", "left"), step.get("count", 1))
        extra = {"screen": [sx, sy]}
    elif act == "wheelclient":
        h = step.get("hwnd") or STATE.get("main_hwnd")
        if not h:
            raise RuntimeError("no hwnd for wheelclient")
        sx, sy = wu.client_to_screen(int(h), int(step["x"]), int(step["y"]))
        wheel_action(step["notches"], sx, sy, step.get("settle_ms"))
        extra = {"screen": [sx, sy]}
    elif act == "pkey":
        h = _resolve_hwnd(step)
        vk = step.get("vk", VK_MAP.get(step.get("name", "").upper(), 0))
        n = step.get("times", 1)
        for _ in range(n):
            user32.PostMessageW(int(h), 0x0100, vk, 0)   # WM_KEYDOWN
            user32.PostMessageW(int(h), 0x0101, vk, 0)   # WM_KEYUP
            if step.get("interval_ms"):
                time.sleep(step["interval_ms"] / 1000.0)
        extra = {"hwnd": h, "vk": vk, "times": n}
    elif act == "pwheel":
        h = _resolve_hwnd(step)
        notches = int(step.get("notches", -1))
        delta = (notches * 120) & 0xFFFFFFFF
        wp = (0 << 16) | (delta >> 16) if False else ((delta & 0xFFFF) << 16)
        # WM_MOUSEWHEEL wParam: high-word = wheel delta; low-word = keys
        wp = ((delta & 0xFFFFFFFF) >> 16) << 16
        lp = ((int(step.get("y", 400)) & 0xFFFF) << 16) | (int(step.get("x", 200)) & 0xFFFF)
        for _ in range(int(step.get("times", 1))):
            user32.PostMessageW(int(h), 0x020A, wp, lp)
            if step.get("interval_ms"):
                time.sleep(step["interval_ms"] / 1000.0)
        extra = {"hwnd": h, "notches": notches, "wp": hex(wp), "lp": hex(lp)}
    elif act == "close":
        wu.close_window(int(step["hwnd"]))
    else:
        raise ValueError("unknown action: %r" % act)
    # optional auto-shot attached to any step
    if step.get("shot"):
        extra["shot"] = shot(step["shot"], step.get("shot_hwnd"),
                             step.get("shot_rect"), step.get("shot_scale", 1))
    return extra


def execute(cmd):
    result = {"id": cmd.get("id"), "ok": False, "steps": []}
    try:
        steps = cmd.get("steps") or [cmd]
        for i, step in enumerate(steps):
            t0 = time.time()
            info = {}
            try:
                info = run_step(step, i)
                ok = True
                err = None
            except Exception as exc:  # keep going; record failure
                ok = False
                err = "%s: %s" % (type(exc).__name__, exc)
                traceback.print_exc()
            info.update({"i": i, "action": step.get("action"), "ok": ok,
                         "err": err, "ms": int((time.time() - t0) * 1000)})
            result["steps"].append(info)
            if not ok and cmd.get("stop_on_error"):
                break
        result["ok"] = all(s["ok"] for s in result["steps"])
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        traceback.print_exc()
    return result


def main():
    last_id = None
    print("[worker] up in session; screen=%sx%s" % (
        user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)), flush=True)
    while not STOP.exists():
        try:
            raw = CMD.read_text(encoding="utf-8")
            cmd = json.loads(raw)
        except Exception:
            time.sleep(0.25)
            continue
        if cmd.get("id") == last_id or cmd.get("id") is None:
            time.sleep(0.25)
            continue
        last_id = cmd.get("id")
        if cmd.get("action") == "die":
            (OUT / ("result_%s.json" % last_id)).write_text(
                json.dumps({"id": last_id, "ok": True, "bye": True}),
                encoding="utf-8")
            break
        result = execute(cmd)
        (OUT / ("result_%s.json" % last_id)).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[worker] exit", flush=True)


if __name__ == "__main__":
    main()
