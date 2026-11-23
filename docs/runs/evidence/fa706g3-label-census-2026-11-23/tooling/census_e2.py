# -*- coding: utf-8 -*-
"""census_e2.py — task E2 label census driver (session-0 side).

E2 rewrite of census.py cmd_census with the anti-interruption rules:
  * partial JSON (census_<tab>.partial.json, atomic replace) flushed after
    EVERY scrolled frame + a sidebar crop PNG per OCR'd frame in the worker
    out dir
  * hard per-page budget (default 25 min) -> final JSON with complete=false
    and stopped_at (offset + viewport rows) instead of nothing on disk
  * start-of-page reset: tab away + back (panel rebuild = page top),
    confirmed by up-rolls staying put
  * movement judged by row displacement (text-identical rows), not the raw
    frame signature — the signature jitters at the page bottom and burned
    the whole per-walk roll cap on Strength
Everything else (launch/advanced/close protocol, worker) is reused from
census.py in this directory.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import census as C  # noqa: E402

WHEEL_PTS = [(300, 880), (300, 1000), (300, 800), (350, 940), (150, 900)]
SIDEBAR_RECT = [8, 712, 434, 1040]   # refined after orient 2026-11-23
STATIC_DY = 8          # |displacement| below this = same position (OCR jitter)
BOTTOM_AGREE_PX = 60


def cmd_census(tab, psm=6, max_steps=1200, budget_s=1500.0):
    t_start = time.time()
    st = C.load_state()
    hwnd = st["main_hwnd"]
    sb = st.get("sidebar_rect", SIDEBAR_RECT)
    other = C.TABS[(C.TABS.index(tab) + 1) % len(C.TABS)]
    low = tab.lower()
    C.EV.mkdir(parents=True, exist_ok=True)
    final_json = C.EV / f"census_{low}.json"
    partial_json = C.EV / f"census_{low}.partial.json"

    pti = [0]
    total = [0]          # wheel notches sent
    frames = []          # (offset, lines, walk)
    notes, stops, shots = [], [], []
    n_shots = [0]
    n_fshots = [0]
    jitters = [0]
    walks = [0]
    complete = [False]
    stop_info = [None]
    reason = [""]

    def left():
        return budget_s - (time.time() - t_start)

    def run(steps, what, tries=3):
        for attempt in range(tries):
            try:
                res = C.send(steps)
                if res.get("ok"):
                    return res
                errs = [s.get("err") for s in res.get("steps", [])
                        if not s.get("ok")]
                raise RuntimeError(f"{what} failed: {errs}")
            except Exception as exc:
                notes.append(f"{what} attempt {attempt + 1}: "
                             f"{type(exc).__name__}: {exc}")
                time.sleep(2.0)
                try:
                    C.send([{"action": "ping"}], wait_s=15)
                except Exception:
                    notes.append("worker ping timeout; waiting 15s")
                    time.sleep(15)
        raise RuntimeError(f"{what}: worker failing after {tries} tries")

    def ocr_step():
        return {"action": "ocr", "name": "census_probe", "hwnd": hwnd,
                "psm": psm, "scale": 3, "rect": list(sb)}

    def wheel_step(notches, pt):
        total[0] += 1
        return {"action": "wheelclient", "hwnd": hwnd, "x": pt[0], "y": pt[1],
                "notches": notches, "settle_ms": 550}

    def fshot_step():
        """Sidebar crop of the frame about to be OCR'd (same roundtrip)."""
        n_fshots[0] += 1
        return {"action": "shot", "name": f"census_{low}_f{n_fshots[0]:03d}",
                "hwnd": hwnd, "rect": list(sb), "scale": 2}

    def grab(extra=None):
        res = run(list(extra or []) + [fshot_step(), ocr_step()], "frame")
        return C.lines_from_words(res["steps"][-1]["words"])

    def snap(tag):
        if n_shots[0] >= 3:
            return
        name = f"census_{low}_{tag}"
        run([{"action": "shot", "name": name, "hwnd": hwnd}], f"shot {tag}")
        shots.append(name + ".png")
        n_shots[0] += 1
        src = C.OUT / (name + ".png")
        if src.exists():
            shutil.copy(src, C.EV / (name + ".png"))

    def displacement(prev, cur):
        """Viewport dy of text-identical rows; 0 = same position."""
        dy = C.estimate_shift(prev, cur)
        return dy if abs(dy) >= STATIC_DY else 0

    def flush(final=False):
        rows = C.merge_frames_abs([(o, ln) for o, ln, _w in frames])
        doc = {
            "tab": tab,
            "version": C.VERSION,
            "build": C.BUILD,
            "captured": time.strftime("%Y-%m-%d %H:%M"),
            "channel": ("zcode_gui_task session-1 worker: real SendInput wheel "
                        "(1 notch/step, >=550ms settle), PrintWindow capture, "
                        f"pytesseract eng psm={psm} scale=3; E2 driver: "
                        "per-frame partial flush, movement judged by row "
                        "displacement, page reset by tab rebuild"),
            "psm": psm,
            "complete": bool(complete[0]),
            "stop_reason": reason[0],
            "stopped_at": stop_info[0],
            "walks": walks[0],
            "wheel_steps": total[0],
            "scroll_px_per_notch": 60,
            "row_y_space": ("page-absolute px reconstructed from frame "
                            "displacement; viewport y = row y - offset of the "
                            "frame it was read in"),
            "rows": [{"text": t, "y": y} for y, t in rows],
            "row_count": len(rows),
            "frames": [{"step": i, "walk": w, "offset": o,
                        "lines": [[t, wy] for _, t, wy in ln]}
                       for i, (o, ln, w) in enumerate(frames)],
            "shots": list(shots),
            "frame_shots": (str(C.OUT) + "\\census_" + low
                            + "_f*.png (sidebar crop scale 2, "
                            "one per OCR'd frame)"),
            "frame_shots_count": n_fshots[0],
            "frame_jitters": jitters[0],
            "notes": list(notes),
            "raw": "OCR text preserved verbatim (misreads included) "
                   "per task E spec",
        }
        path = final_json if final else partial_json
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
        if final and partial_json.exists():
            partial_json.unlink()
        return len(rows)

    def fgmain():
        run([{"action": "fgmain"}], "fgmain")

    def tab_click(t):
        for attempt in range(3):
            try:
                C.click_tab(t)
                return
            except Exception as exc:
                notes.append(f"click tab {t} attempt {attempt + 1}: {exc}")
                time.sleep(2.0)
        raise RuntimeError(f"click tab {t} failing")

    def at_top(walk):
        """Tab away+back rebuilds the panel at page top; confirm by
        up-rolls staying put (2 consecutive static)."""
        tab_click(other)
        tab_click(tab)
        fgmain()
        cur = grab()
        static = 0
        rolls = 0
        while static < 2 and rolls < 40 and left() > 60:
            nxt = grab([wheel_step(+1, WHEEL_PTS[rolls % 2])])
            rolls += 1
            if displacement(cur, nxt):
                static = 0
            else:
                static += 1
            cur = nxt
        top3 = [t for _, t, _ in cur[:3]]
        notes.append(f"walk{walk}: top after {rolls} up-rolls "
                     f"({static} static): {top3}")
        return cur

    def step_down(cur):
        """One notch down through the wheel points. Returns (lines, dy):
        dy < 0 moved; 0 = static after every point."""
        for k in range(len(WHEEL_PTS)):
            if left() <= 20:
                return cur, 0
            pt = WHEEL_PTS[(pti[0] + k) % len(WHEEL_PTS)]
            nxt = grab([wheel_step(-1, pt)])
            dy = displacement(cur, nxt)
            if dy:
                if k:
                    pti[0] = (pti[0] + k) % len(WHEEL_PTS)
                return nxt, dy
            jitters[0] += 1
            cur = nxt
        return cur, 0

    reason[0] = "not started"
    stop_info[0] = {"walk": 0, "offset": 0}
    try:
        while total[0] < max_steps and left() > 60:
            walks[0] += 1
            walk = walks[0]
            cur = at_top(walk)
            if walk == 1:
                snap("top")
            frames.append((0, cur, walk))
            flush()
            offset = 0
            stop_kind = "budget"
            while total[0] < max_steps:
                nxt, dy = step_down(cur)
                if not dy:
                    if left() <= 60:
                        break
                    fgmain()
                    nxt, dy = step_down(cur)
                    if dy:
                        notes.append(f"walk{walk}: fgmain revived at "
                                     f"offset={offset}")
                if not dy:
                    stop_kind = "static"
                    break
                offset += -dy
                cur = nxt
                frames.append((offset, cur, walk))
                flush()
                if walk == 1 and n_shots[0] == 1 and offset >= 240:
                    snap("mid")
            stop_info[0] = {"walk": walk, "offset": offset, "kind": stop_kind,
                            "viewport_rows": [[t, wy] for _, t, wy in cur]}
            if stop_kind == "budget":
                reason[0] = ("page budget exhausted before bottom "
                             f"(offset={offset}px, walk {walk})")
                notes.append(reason[0])
                break
            stops.append(offset)
            notes.append(f"walk{walk}: stop at offset={offset}px "
                         f"(primary pt {WHEEL_PTS[pti[0]]})")
            flush()
            if len(stops) >= 2 and abs(stops[-1] - stops[-2]) <= BOTTOM_AGREE_PX:
                complete[0] = True
                reason[0] = (f"bottom confirmed: stops {stops[-2:]} agree "
                             f"within {BOTTOM_AGREE_PX}px")
                notes.append(reason[0])
                break
            if left() <= 120:
                reason[0] = (f"page budget left {int(left())}s: stop "
                             f"{offset}px unconfirmed by a second walk")
                notes.append(reason[0])
                break
        else:
            if not complete[0]:
                reason[0] = ("roll cap hit" if total[0] >= max_steps
                             else "page budget exhausted before a walk")
    except Exception as exc:
        reason[0] = f"{type(exc).__name__}: {exc}"
        notes.append(reason[0])
    stop_info_d = dict(stop_info[0] or {})
    stop_info_d["walk_stops"] = list(stops)
    stop_info[0] = stop_info_d
    snap("bottom")
    n = flush(final=True)
    print(f"[census:{tab}] rows={n} walks={walks[0]} steps={total[0]} "
          f"stops={stops} complete={complete[0]} reason={reason[0]!r}",
          flush=True)
    print(json.dumps({"notes": notes}, ensure_ascii=False), flush=True)
    return 0 if complete[0] else 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ping", "seed", "launch", "orient",
                                    "tabrow", "advanced", "census", "close"])
    ap.add_argument("--tab")
    ap.add_argument("--psm", type=int, default=6)
    ap.add_argument("--budget", type=float, default=1500.0,
                    help="per-page budget in seconds (default 25 min)")
    a = ap.parse_args()
    C.TASKDIR.mkdir(parents=True, exist_ok=True)
    if a.cmd == "census":
        sys.exit(cmd_census(a.tab, psm=a.psm, budget_s=a.budget))
    {"ping": C.cmd_ping, "seed": C.cmd_seed, "launch": C.cmd_launch,
     "orient": C.cmd_orient, "tabrow": C.cmd_tabrow,
     "advanced": C.cmd_advanced, "close": C.cmd_close}[a.cmd]()


if __name__ == "__main__":
    main()
