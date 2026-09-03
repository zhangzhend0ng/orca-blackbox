#!/usr/bin/env python3
"""blocker_sweep_check.py — deterministic check of the launch boot-blocker
sweep mechanics (PITFALLS_0901.md 19, launcher.sweep_boot_blockers).

Why not a real Orca boot: the incident dialog (MsgUpdateConfig) is driven by
the preset-updater feed (https://api.bambulab.com — not conf-stubbable), and
the app-version feed trick (orca_upgrade_url -> localhost, boot_probe phase
b) was never proven to reach a dialog (measured 09-03: no dialog, no fetch
evidence; the AppConfig::get section behavior for that key is unverified).
So this check synthesizes the blocker SIGNATURE instead — a real native
#32770 dialog (MessageBoxW runs its own message pump) titled exactly like
the sweep's targets, in the sweep's own process (sweep scopes to the app
pid; same-process windows are in scope):

  ignore — dialog titled 'Unrelated Caption' must SURVIVE a sweep
  dismiss — dialog titled 'Configuration update' must be WM_CLOSEd by the
            sweep (returns from its MessageBox thread) and be recorded in
            the dismissed list; the unrelated dialog stays up
  version — dialog titled 'New version of Snapmaker Orca' must be
            WM_CLOSEd too (the UpdateVersionDialog family; WM_CLOSE on the
            REAL dialog was proven app-safe by boot_probe phase b's
            close_test — this phase pins the sweep-title mechanics for it)

ASCII stdout; exit 0 = pass, 1 = fail. Runs under the INTERACTIVE scheduled
task 'blocker_check' (PITFALLS 18.7: window enumeration needs the desktop).
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import launcher  # noqa: E402

MB_OKCANCEL = 0x01
WM_CLOSE = 0x0010
INVALID_HWND = -1  # MessageBoxW returns 0 on failure; IDs are >0


def _message_box_thread(title: str, result: list[int]) -> None:
    """Blocking MessageBoxW in a worker thread (Windows pumps it for us)."""
    result.append(ctypes.windll.user32.MessageBoxW(None, "blocker_sweep_check body", title, MB_OKCANCEL))


def open_dialog(title: str) -> tuple[list[int], threading.Thread]:
    result: list[int] = []
    thread = threading.Thread(target=_message_box_thread, args=(title, result), daemon=True)
    thread.start()
    return result, thread


def find_dialogs(title: str, timeout_s: float = 5.0) -> list[int]:
    """hwnds of visible top-level windows with exactly this title."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hits = [h for h, p in launcher.winutil.enum_windows()
                if launcher.winutil.window_title(h) == title]
        if hits:
            return hits
        time.sleep(0.2)
    return []


def run_ignore_phase() -> bool:
    print("== phase ignore: unmatched dialog must survive the sweep ==", flush=True)
    result, thread = open_dialog("Unrelated Caption")
    hits = find_dialogs("Unrelated Caption")
    ok_present = bool(hits)
    # main_hwnd=0: the unrelated box is genuinely title-matched (not merely
    # excluded) — this is what proves BLOCKER_TITLES discrimination
    dismissed = launcher.sweep_boot_blockers(pid=os.getpid(),
                                             main_hwnd=0,
                                             budget_s=4.0)
    ok_dismissed = dismissed == []
    alive = bool(find_dialogs("Unrelated Caption", timeout_s=1.0))
    ok = ok_present and ok_dismissed and alive
    if hits:
        ctypes.windll.user32.PostMessageW(hits[0], WM_CLOSE, 0, 0)
    thread.join(timeout=5.0)
    print(f"   present={ok_present} dismissed={dismissed} survived={alive} -> "
          f"{'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def run_dismiss_phase(title: str) -> bool:
    print(f"== phase dismiss: titled blocker '{title}' must be WM_CLOSEd "
          f"and recorded ==", flush=True)
    result, thread = open_dialog(title)
    hits = find_dialogs(title)
    ok_present = bool(hits)
    dismissed = launcher.sweep_boot_blockers(pid=__import__("os").getpid(),
                                             main_hwnd=0,
                                             budget_s=4.0)
    thread.join(timeout=5.0)  # MessageBox worker must have returned
    ok_dismissed = any(t == title.lower() for t in dismissed)
    gone = not find_dialogs(title, timeout_s=2.0)
    box_returned = bool(result)  # MessageBoxW returned = dialog really closed
    ok = ok_present and ok_dismissed and gone and box_returned
    print(f"   present={ok_present} dismissed={dismissed} gone={gone} "
          f"box_returned={box_returned} thread_alive={thread.is_alive()} -> "
          f"{'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main() -> int:
    results = {
        "ignore": run_ignore_phase(),
        "dismiss": run_dismiss_phase("Configuration update"),
        "version": run_dismiss_phase("New version of Snapmaker Orca"),
    }
    verdict = all(results.values())
    print(f"===== blocker_sweep_check verdict: {'PASS' if verdict else 'FAIL'} "
          f"(phases={results}) =====", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
