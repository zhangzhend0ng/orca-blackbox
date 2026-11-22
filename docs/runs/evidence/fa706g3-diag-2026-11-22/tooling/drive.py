# -*- coding: utf-8 -*-
"""drive.py — session-0 orchestrator over the fa706_diag session-1 worker.

Writes cmd.json commands, polls out/result_<id>.json, analyzes OCR JSON.
NO window/GUI calls in this process (session 0 cannot touch session-1
windows); everything on the desktop goes through the worker's steps.
"""
import json
import shutil
import sys
import time
from pathlib import Path

BASE = Path(r"C:\coil\fa706_diag")
OUT = BASE / "out"
CMD = BASE / "cmd.json"
EV = Path(r"C:\coil\orca-blackbox-v3-r1\docs\runs\evidence\fa706g3-diag-2026-11-22")

_next_id = [int(time.time()) % 100000]


def send(steps, wait_s=120.0):
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
            time.sleep(0.2)  # let the write finish
            return json.loads(res_path.read_text(encoding="utf-8"))
        time.sleep(0.25)
    raise TimeoutError(f"worker did not answer cmd {cid} in {wait_s}s")


def archive_cmd(cid):
    shutil.copy(CMD, BASE / f"cmd{cid}.json")


def ocr_lines(words, row_tol=14):
    """Group OCR words [text,x,y,w,h,conf] into visual lines."""
    rows = {}
    for t, x, y, w, h, c in words:
        rows.setdefault(round(y / row_tol) * row_tol, []).append((x, t))
    return [" ".join(t for _, t in sorted(v)) for k, v in sorted(rows.items())]


def ev_copy(png_name, tag):
    """Copy a worker screenshot into the repo evidence dir."""
    EV.mkdir(parents=True, exist_ok=True)
    src = OUT / png_name
    if src.exists():
        shutil.copy(src, EV / f"{tag}.png")
        return f"docs/runs/evidence/fa706g3-diag-2026-11-22/{tag}.png"
    return None
