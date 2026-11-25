#!/usr/bin/env python3
# m7x_140_close_without_residue.py — Close Orca from its topbar and check the whole process list.
# feishu: baseline#140

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import m7_common as m7
from harness import launcher, topbar_util, winutil
from harness.anchors import TAB_PREPARE_ACTIVE, wait_for
from m3_common import add_common_args, boot_session


def process_snapshot():
    command = ("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | "
               "Select-Object Name,ProcessId,ParentProcessId,SessionId,CreationDate | "
               "ConvertTo-Json -Depth 3 -Compress")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=True, timeout=10)
    return {row["ProcessId"]: row for row in json.loads(result.stdout)}


def orca_pids(snapshot, image):
    names = {"snapmaker-orca.exe", image.casefold()}
    return sorted(pid for pid, row in snapshot.items() if row["Name"].casefold() in names)


def process_family(snapshot, parent):
    found = {parent}
    while True:
        known = found | {pid for pid, row in snapshot.items() if row["ParentProcessId"] in found}
        if known == found:
            return {pid: snapshot[pid] for pid in known if pid in snapshot}
        found = known


def remaining_processes(snapshot, family, image):
    return sorted(set(orca_pids(snapshot, image)) | {
        pid for pid, row in family.items() if pid in snapshot
        and snapshot[pid]["CreationDate"] == row["CreationDate"]
    })


def close_glyph(frame):
    """Locate the X in Orca's rightmost toolbar tool, using both diagonal arms."""
    height, width = frame.shape[:2]
    gray = frame[:, :, :3].mean(axis=2)
    bg = float(np.median(gray[:, -40:]))
    ink = np.abs(gray - bg) >= 35
    best = (0, 0, 0)
    for y in range(max(5, height // 2 - 3), min(height - 5, height // 2 + 4)):
        for x in range(width - 29, width - 6):
            score = min(sum(ink[y + k, x + sign * k] for k in (-4, -3, -2, 2, 3, 4))
                        for sign in (1, -1))
            if score > best[0]:
                best = (score, x, y)
    return best


def click_close_tool(session):
    topbar = topbar_util._topbar(session.hwnd)
    if not topbar:
        raise RuntimeError("top toolbar not found")
    _, (left, top, right, bottom), toolbar = topbar
    width, height, raw = winutil.capture_window(toolbar)
    frame = np.frombuffer(raw, np.uint8).reshape(height, width, 4)
    score, x, y = close_glyph(frame)
    if score < 4:
        # Some wx builds only paint the composed frame, so read the same strip
        # in the main-window capture using its client origin.
        origin_x, origin_y = winutil.client_to_screen(session.hwnd, 0, 0)
        frame = m7.capture_bgr(session)[top - origin_y:bottom - origin_y,
                                       left - origin_x:right - origin_x]
        score, x, y = close_glyph(frame)
    origin_x, origin_y = winutil.client_to_screen(toolbar, 0, 0)
    point = (origin_x + x, origin_y + y)
    target = winutil.deepest_child_at(session.hwnd, *point)
    print(f"[m7x140] topbar={topbar[1]}, close X score={score}/6, point={point}, "
          f"toolbar={toolbar:#x}, target={target:#x}")
    if score < 4 or target != toolbar:
        return False
    # BBLTopbar resolves its tools against the system cursor position.
    if not winutil.user32.SetCursorPos(*point):
        return False
    winutil.msg_click_screen(*point, session.hwnd)
    return True


def main():
    args = add_common_args(argparse.ArgumentParser()).parse_args()
    exe = Path(args.exe) if args.exe else launcher.default_exe()
    before = orca_pids(process_snapshot(), exe.name)
    print(f"[m7x140] machine={os.environ.get('COMPUTERNAME')!r}, images before launch={before}")
    if before:
        return m7.m7_verdict({"clean process baseline": "FAIL"})

    session = boot_session(args, model=None)
    try:
        prepare_score, *_ = wait_for(session, TAB_PREPARE_ACTIVE, timeout_s=30)
        snapshot = process_snapshot()
        observed = orca_pids(snapshot, exe.name)
        identity = snapshot.get(session.pid, {})
        print(f"[m7x140] Prepare score={prepare_score:.3f}, own pid={session.pid}, "
              f"system process={identity}, all Orca images={observed}, "
              f"exe={exe}, isolated profile={args.datadir}")
        if prepare_score < 0.8 or observed != [session.pid] or not session.alive():
            return m7.m7_verdict({"ready page and own Orca process": "FAIL"})
        family = process_family(snapshot, session.pid)
        print(f"[m7x140] pre-close process family={[(pid, item['Name']) for pid, item in family.items()]}")
        started = time.monotonic()
        clicked = click_close_tool(session)
        if not clicked:
            return m7.m7_verdict({"upper-right Close tool clicked": "FAIL"})
        try:
            exit_code = session.popen.wait(timeout=20)
        except subprocess.TimeoutExpired:
            exit_code = None
        window_closed = not winutil.user32.IsWindow(session.hwnd)
        print(f"[m7x140] before any cleanup: window_closed={window_closed}, "
              f"exit_code={exit_code!r}, elapsed={time.monotonic() - started:.3f}s")
        samples = []
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            samples.append(remaining_processes(process_snapshot(), family, exe.name))
            if len(samples) >= 2 and samples[-2:] == [[], []]:
                break
            time.sleep(0.7)
        print(f"[m7x140] machine-wide post-close process residue samples={samples}")
        return m7.m7_verdict({
            "Prepare page and launched Orca process observed": "PASS",
            "upper-right Close tool clicked": "PASS",
            "window and process exit normally": "PASS" if window_closed and exit_code == 0 else "FAIL",
            "no Orca image or process-family residue": "PASS" if samples[-2:] == [[], []] else "FAIL",
        })
    finally:
        if session.alive():
            print("[m7x140] beginning cleanup after observation of failed exit")
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
