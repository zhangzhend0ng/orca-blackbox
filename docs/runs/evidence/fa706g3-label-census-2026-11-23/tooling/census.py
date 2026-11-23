# -*- coding: utf-8 -*-
"""census.py — task E label census driver (session-0 side).

Drives the fa706_diag session-1 worker (zcode_gui_task scheduled task,
cmd.json polling protocol) to walk the six Advanced-mode parameter tabs of
Orca 2.3.5 with single-notch wheel steps and OCR every frame. Raw OCR text
is preserved verbatim (misreads included) — it IS the deliverable.

No GUI calls in this process (session 0); everything desktop-side goes
through worker steps. State persists in state.json between invocations.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"C:\coil\fa706_diag")
OUT = BASE / "out"
CMD = BASE / "cmd.json"
TASKDIR = Path(r"C:\coil\fa706_taskE")
STATE = TASKDIR / "state.json"
REPO = Path(r"C:\coil\orca-blackbox-v3-r1")
EV = REPO / "docs" / "runs" / "evidence" / "fa706g3-label-census-2026-11-23"
EXE = Path(r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe")
DATADIR = TASKDIR / "profile_e"
MODEL = REPO / "fixtures" / "agent_layer_cube.3mf"

TABS = ["Quality", "Strength", "Speed", "Support", "Multimaterial", "Others"]
VERSION = "2.3.5-nightly"
BUILD = "01.10.01.50"

_next_id = [int(time.time()) % 100000]


def send(steps, wait_s=180.0):
    _next_id[0] += 1
    cid = _next_id[0]
    res_path = OUT / f"result_{cid}.json"
    if res_path.exists():
        res_path.unlink()
    CMD.write_text(json.dumps({"id": cid, "steps": steps}, ensure_ascii=False),
                   encoding="utf-8")
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if res_path.exists():
            time.sleep(0.2)
            return json.loads(res_path.read_text(encoding="utf-8"))
        time.sleep(0.25)
    raise TimeoutError(f"worker did not answer cmd {cid} in {wait_s}s")


def save_state(**kw):
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    st.update(kw)
    STATE.write_text(json.dumps(st), encoding="utf-8")


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def check(res, what):
    if not res.get("ok"):
        errs = [s.get("err") for s in res.get("steps", []) if not s.get("ok")]
        raise RuntimeError(f"{what} failed: {errs}")
    return res


# ------------------------------------------------------------------ OCR utils
def sidebar_words(rect=None, psm=6, scale=3):
    st = load_state()
    step = {"action": "ocr", "name": "census_probe", "hwnd": st["main_hwnd"],
            "psm": psm, "scale": scale}
    if rect:
        step["rect"] = list(rect)
    res = check(send([step]), "ocr")
    return res["steps"][0]["words"]


def lines_from_words(words, row_tol=12):
    """Group [text,x,y,w,h,conf] into visual lines -> [(y, text)]."""
    rows = {}
    for t, x, y, w, h, c in words:
        key = round(y / row_tol) * row_tol
        rows.setdefault(key, []).append((x, t, y))
    out = []
    for key in sorted(rows):
        ws = sorted(rows[key])
        out.append((key, " ".join(t for _, t, _ in ws), round(ws[0][2])))
    return out


def frame_sig(lines):
    return "\n".join(t for _, t, _ in lines)


def merge_frames(frames, bucket=10):
    """frames: list of line lists -> merged rows [(y, text)] keeping the
    longest text seen per y-bucket (OCR of a partially visible row can be
    truncated; later frames usually see it whole)."""
    best = {}
    for lines in frames:
        for by, text, wy in lines:
            key = round(wy / bucket) * bucket
            if key not in best or len(text) > len(best[key][1]):
                best[key] = (wy, text)
    return sorted(best.values())


def estimate_shift(prev_lines, cur_lines):
    """Most common viewport-y delta of text-identical rows between frames.
    0 when the frame did not move (freeze or true bottom)."""
    from collections import Counter
    cur_by_text = {}
    for by, t, wy in cur_lines:
        cur_by_text.setdefault(t, []).append(wy)
    dys = []
    for by, t, wy in prev_lines:
        if t in cur_by_text:
            dys.append(cur_by_text[t][0] - wy)
    if not dys:
        return 0
    return Counter(dys).most_common(1)[0][0]


def merge_frames_abs(frames, bucket=8):
    """frames: [(offset, lines)] with page-absolute offset -> rows [(y, text)].
    Dedup by absolute-y bucket, keep the longest OCR text seen (a partially
    visible row often reads truncated; another frame sees it whole)."""
    best = {}
    for offset, lines in frames:
        for by, t, wy in lines:
            ay = offset + wy
            key = round(ay / bucket) * bucket
            if key not in best or len(t) > len(best[key][1]):
                best[key] = (ay, t)
    return sorted(best.values())


# ------------------------------------------------------------------- actions
def cmd_ping():
    res = send([{"action": "ping"}], wait_s=15)
    print(json.dumps(res, ensure_ascii=False))


def cmd_seed():
    import os
    sys.path.insert(0, str(REPO))
    os.environ["ORCA_BB_ALLOW_HOST"] = "1"
    from harness.profile import seed_profile
    seed_profile(DATADIR, fresh=True)
    print(f"[seed] {DATADIR}")


def cmd_launch():
    res = check(send([
        {"action": "launch", "exe": str(EXE), "datadir": str(DATADIR),
         "model": str(MODEL)},
        {"action": "sweep", "budget_s": 15.0},
        {"action": "sleep", "ms": 2500},
        {"action": "max"},
    ], wait_s=150), "launch")
    info = res["steps"][0]
    save_state(pid=info["pid"], main_hwnd=info["main_hwnd"], rect=info["rect"])
    print(json.dumps(info, ensure_ascii=False))


def cmd_orient():
    """Full-window OCR + shot; report the sidebar x-extent and the tab row."""
    st = load_state()
    res = check(send([
        {"action": "shot", "name": "census_orient", "hwnd": st["main_hwnd"]},
        {"action": "ocr", "name": "census_orient", "hwnd": st["main_hwnd"],
         "psm": 3, "scale": 2},
    ]), "orient")
    words = res["steps"][1]["words"]
    for t, x, y, w, h, c in words:
        if x < 460 and 560 < y < 720:
            print(f"  {t!r:30} x={x:4} y={y:4} w={w:3} conf={c}")
    save_state(orient_words=[[t, x, y, w, h, c] for t, x, y, w, h, c in words])


def find_word(words, needle, x_max=460, y_min=0, y_max=2000):
    cands = [w for w in words if needle.lower() in w[0].lower()
             and w[1] < x_max and y_min < w[2] < y_max]
    return cands


def cmd_tabrow():
    """OCR the tab strip; report which tabs are visible (advanced or not)."""
    words = sidebar_words(rect=[180, 580, 460, 700])
    for t, x, y, w, h, c in words:
        print(f"  {t!r:20} x={x:4} y={y:4} conf={c}")


def cmd_advanced():
    """Toggle the Advanced switch on if the tab row lacks Speed/Others."""
    words = sidebar_words(rect=[180, 560, 460, 720])
    text = " ".join(w[0] for w in words).lower()
    if "speed" in text and "others" in text:
        print("[advanced] already on")
        save_state(advanced=True)
        return
    cand = find_word(words, "advanced", x_max=460, y_min=560, y_max=700)
    if not cand:
        raise RuntimeError(f"Advanced label not found: {words}")
    t, x, y, w, h, c = cand[0]
    st = load_state()
    check(send([
        {"action": "clickclient", "hwnd": st["main_hwnd"], "x": x + w // 2 + 45,
         "y": y + h // 2},
        {"action": "sleep", "ms": 2000},
    ]), "advanced click")
    words2 = sidebar_words(rect=[180, 560, 460, 720])
    text2 = " ".join(w[0] for w in words2).lower()
    ok = "speed" in text2 and "others" in text2
    save_state(advanced=ok)
    print(f"[advanced] after toggle: {text2!r} ok={ok}")
    if not ok:
        raise RuntimeError("Advanced toggle did not reveal 6-tab row")


TAB_FUZZ = {"Quality": ("quality",), "Strength": ("strength",),
            "Speed": ("speed",), "Support": ("support",),
            "Multimaterial": ("multimaterial", "multi material", "multimat",
                              "maultimaterial"),
            "Others": ("others", "other", "oth")}
# measured 2026-11-23 advanced-mode tab centers (client coords, y=697)
TAB_XY = {"Quality": (43, 697), "Strength": (111, 697), "Speed": (171, 697),
          "Support": (238, 697), "Multimaterial": (325, 697),
          "Others": (403, 697)}


def click_tab(tab):
    words = sidebar_words(rect=[0, 676, 460, 712], psm=6, scale=4)
    got = False
    for pat in TAB_FUZZ[tab]:
        cand = [w for w in words if w[0].lower().startswith(pat)
                or pat in w[0].lower()]
        if cand:
            t, x, y, w, h, c = cand[0]
            cx, cy = x + w // 2, y + h // 2 + 3
            got = True
            break
    if not got:
        cx, cy = TAB_XY[tab]
        print(f"[tab] {tab} OCR-miss; fallback click ({cx},{cy}) from "
              f"{[(w[0], w[1]) for w in words]}")
    st = load_state()
    check(send([
        {"action": "clickclient", "hwnd": st["main_hwnd"],
         "x": cx, "y": cy},
        {"action": "sleep", "ms": 1800},
    ]), f"click tab {tab}")
    return True


SIDEBAR_RECT = [196, 700, 432, 1040]   # refined after orient
WHEEL_PT = (300, 900)                  # client coords, sidebar body


def cmd_census(tab, psm=6, max_steps=1200):
    st = load_state()
    click_tab(tab)
    sb = st.get("sidebar_rect", SIDEBAR_RECT)
    other = TABS[(TABS.index(tab) + 1) % len(TABS)]

    # wheel points cycle: freeze is cursor-region dependent (Strength:
    # y=880 dead, y=1000 alive); the last working point stays primary
    PTS = [(300, 880), (300, 1000), (300, 800), (350, 940), (150, 900)]
    pti = [0]

    def frame():
        return lines_from_words(sidebar_words(rect=sb, psm=psm))

    def roll(notches, pt=None):
        x, y = pt or PTS[pti[0]]
        check(send([{"action": "wheelclient", "hwnd": st["main_hwnd"],
                     "x": x, "y": y,
                     "notches": notches, "settle_ms": 550}]), "wheel")

    def roll_until_move(notches, cur, count=False):
        """Roll through wheel points until the frame changes. Returns
        (lines, moved) and adapts the primary point."""
        for k in range(len(PTS)):
            roll(notches, PTS[(pti[0] + k) % len(PTS)])
            if count:
                nonlocal_total[0] += 1
            nxt = frame()
            if frame_sig(nxt) != frame_sig(cur):
                if k:
                    pti[0] = (pti[0] + k) % len(PTS)
                return nxt, True
            time.sleep(0.25)
        return cur, False

    nonlocal_total = [0]
    frames = []          # (offset, lines) across all walks
    notes = []
    stops = []           # offsets where a walk's ladder failed
    walks = 0
    total_steps = 0
    shots = []
    n_shots = 0

    def snap(tag):
        nonlocal n_shots
        if n_shots >= 3:
            return
        name = f"census_{tab.lower()}_{tag}"
        check(send([{"action": "shot", "name": name, "hwnd": st["main_hwnd"]}]),
              "shot")
        shots.append(name + ".png")
        n_shots += 1

    def ensure_top():
        """Up-roll with point cycling + fgmain; 6 static rounds = top."""
        check(send([{"action": "fgmain"}]), "fgmain")
        static = 0
        rolls = 0
        cur = frame()
        while static < 6 and rolls < 60:
            nxt, moved = roll_until_move(+1, cur)
            rolls = nonlocal_total[0]
            if moved:
                static = 0
                cur = nxt
            else:
                static += 1
                check(send([{"action": "fgmain"}]), "fgmain")
                time.sleep(0.5)
        return cur, rolls

    def revive():
        """Panel rebuild via tab away+back — the deep unfreeze."""
        click_tab(other)
        click_tab(tab)
        check(send([{"action": "fgmain"}]), "fgmain")

    # ---- walk loop: each walk anchors at page top (offset 0)
    while total_steps < max_steps:
        walks += 1
        cur, upr = ensure_top()
        if walks == 1:
            snap("top")
            notes.append(f"walk1 top after {upr} rolls: "
                         f"{[t for _, t, _ in cur[:3]]}")
        offset = 0
        frames.append((0, cur))
        walk_steps = 0
        while walk_steps < 400:
            nxt, moved = roll_until_move(-1, cur, count=True)
            walk_steps = nonlocal_total[0]
            total_steps = nonlocal_total[0]
            if not moved:
                # static after all points: fgmain retry, then back-roll
                check(send([{"action": "fgmain"}]), "fgmain")
                time.sleep(0.4)
                nxt, moved = roll_until_move(-1, cur, count=True)
                walk_steps = total_steps = nonlocal_total[0]
                if moved:
                    notes.append(f"walk{walks}: fgmain revived")
            if not moved:
                roll(+1)
                time.sleep(0.5)
                nxt, moved = roll_until_move(-1, cur, count=True)
                walk_steps = total_steps = nonlocal_total[0]
                if moved:
                    notes.append(f"walk{walks}: back-roll nudge moved")
            if not moved:
                stops.append(offset)
                notes.append(f"walk{walks}: stop at offset={offset}px "
                             f"(primary pt {PTS[pti[0]]})")
                break
            dy = estimate_shift(cur, nxt)
            if dy:
                offset += -dy
            cur = nxt
            frames.append((offset, cur))
            if walks == 1 and n_shots < 2 and offset >= 240:
                snap("mid")
        else:
            notes.append(f"walk{walks}: hit per-walk roll cap")
            stops.append(offset)
        last3 = stops[-3:] if len(stops) >= 3 else stops
        if len(stops) >= 2 and max(last3) - min(last3) <= 60:
            notes.append(f"bottom confirmed: stops {stops[-3:]} agree "
                         "within 60px")
            break
        if total_steps >= max_steps:
            notes.append("global roll cap hit")
            break
        revive()
    snap("bottom")

    rows = merge_frames_abs(frames)
    doc = {
        "tab": tab,
        "version": VERSION,
        "build": BUILD,
        "captured": time.strftime("%Y-%m-%d %H:%M"),
        "channel": ("zcode_gui_task session-1 worker: real SendInput wheel "
                    "(1 notch/step, >=550ms settle), PrintWindow capture, "
                    f"pytesseract eng psm={psm} scale=3"),
        "psm": psm,
        "walks": walks,
        "wheel_steps": total_steps,
        "scroll_px_per_notch": 60,
        "row_y_space": ("page-absolute px reconstructed from frame "
                        "displacement; viewport y = row y - offset of the "
                        "frame it was read in"),
        "rows": [{"text": t, "y": y} for y, t in rows],
        "row_count": len(rows),
        "frames": [{"step": i, "offset": o,
                    "lines": [[t, wy] for _, t, wy in ln]}
                   for i, (o, ln) in enumerate(frames)],
        "shots": shots,
        "notes": notes,
        "raw": "OCR text preserved verbatim (misreads included) "
               "per task E spec",
    }
    EV.mkdir(parents=True, exist_ok=True)
    out_json = EV / f"census_{tab.lower()}.json"
    out_json.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    for png in shots:
        src = OUT / png
        if src.exists():
            shutil.copy(src, EV / png)
    print(f"[census:{tab}] rows={len(rows)} walks={walks} "
          f"steps={total_steps} stops={stops} shots={shots}")
    print(json.dumps({"notes": notes}, ensure_ascii=False))


def cmd_close():
    st = load_state()
    if "main_hwnd" in st:
        check(send([{"action": "close", "hwnd": st["main_hwnd"]},
                    {"action": "sleep", "ms": 1500}]), "close")
        # save prompt may appear -> answer No via click is UI-dependent;
        # fall back to taskkill from session 0
    subprocess.run(["taskkill", "/IM", "snapmaker-orca.exe", "/F"],
                   capture_output=True)
    print("[close] done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ping", "seed", "launch", "orient",
                                    "tabrow", "advanced", "census", "close"])
    ap.add_argument("--tab")
    ap.add_argument("--psm", type=int, default=6)
    a = ap.parse_args()
    TASKDIR.mkdir(parents=True, exist_ok=True)
    {"ping": cmd_ping, "seed": cmd_seed, "launch": cmd_launch,
     "orient": cmd_orient, "tabrow": cmd_tabrow, "advanced": cmd_advanced,
     "close": cmd_close,
     "census": lambda: cmd_census(a.tab, psm=a.psm)}[a.cmd]()


if __name__ == "__main__":
    main()
