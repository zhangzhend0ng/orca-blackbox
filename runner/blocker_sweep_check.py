#!/usr/bin/env python3
"""blocker_sweep_check.py — deterministic end-to-end check of the launch
boot-blocker sweep (PITFALLS_0901.md 19, launcher.sweep_boot_blockers).

Discriminating two-phase design (not just "it passed"): the launcher sweep
dismisses the update dialog within ~0.5s of it appearing, so a single
sweep-on boot cannot tell "dismissed" from "never popped". Both phases use
boot_probe's localhost feed trick (9.9.9 non-force via the seed conf knob)
to make the 'Snapmaker Orca Update' dialog (MsgUpdateSlic3r) appear
DETERMINISTICALLY:

  off — launch(dismiss_blockers=False): dialog must APPEAR and SURVIVE 10s
        (proves the feed drives the dialog and the detector below sees it)
  on  — fresh boot, sweep enabled: session.blockers must contain the dialog
        title, and no matching window may survive the sweep

Outputs ASCII lines to stdout (task log); exit 0 = pass, 1 = fail.
Runs under the INTERACTIVE scheduled task 'blocker_check' (PITFALLS 18.7).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "runner"))

from harness import launcher, profile, winutil  # noqa: E402
import boot_probe  # noqa: E402  (runner/ sibling: feed server + payload)

TARGET_TITLE = "snapmaker orca update"  # MsgUpdateSlic3r, lowercased
CONF_EXTRA = {"orca_upgrade_url": f"http://127.0.0.1:{boot_probe.FEED_PORT}/version.json"}
DATADIR = HERE / "artifacts" / "blocker_check_datadir"


def blocker_windows(pid: int) -> list[tuple[int, str]]:
    """Visible app windows whose title matches a blocker signature."""
    hits: list[tuple[int, str]] = []
    for hwnd, wpid in winutil.enum_windows():
        if wpid != pid:
            continue
        title = winutil.window_title(hwnd).strip().lower()
        if title in launcher.BLOCKER_TITLES:
            hits.append((hwnd, title))
    return hits


def wait_blocker(pid: int, timeout_s: float = 30.0) -> list[tuple[int, str]]:
    """Poll until a blocker window is up (the feed check fires a few seconds
    into boot — launch() does not wait for it in the sweep-off phase)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hits = blocker_windows(pid)
        if hits:
            return hits
        time.sleep(0.5)
    return []


def run_phase(sweep_on: bool) -> bool:
    label = "on" if sweep_on else "off"
    print(f"== phase {label}: sweep={'on' if sweep_on else 'off'} ==", flush=True)
    profile.seed_profile(DATADIR, fresh=True, conf_extra=CONF_EXTRA)
    srv = boot_probe.serve_feed(force=False)
    try:
        session = launcher.launch(datadir=DATADIR, boot_demote_s=0,
                                  dismiss_blockers=sweep_on, blocker_sweep_s=20.0)
        if sweep_on:
            # the sweep already ran inside launch(); dismissal is recorded
            # on the session and no matching window may survive
            time.sleep(3.0)  # settle
            survivors = blocker_windows(session.pid)
            dismissed = [t.lower() for t in getattr(session, "blockers", [])]
            ok = TARGET_TITLE in dismissed and not survivors
            print(f"   dismissed={dismissed} survivors={survivors} -> "
                  f"{'PASS' if ok else 'FAIL'}", flush=True)
        else:
            # must APPEAR, then SURVIVE 10s (appearance alone would not
            # discriminate a self-closing transient from a real blocker)
            appeared = wait_blocker(session.pid, timeout_s=30.0)
            time.sleep(10.0)
            survivors = blocker_windows(session.pid)
            ok = bool(appeared) and bool(survivors)
            print(f"   appeared={bool(appeared)} survived_10s={bool(survivors)} -> "
                  f"{'PASS' if ok else 'FAIL'} (dialog expected to persist)", flush=True)
        if session.alive():
            session.close(timeout_s=15.0)
        else:
            print("   app DIED (unexpected for the non-force feed)", flush=True)
            ok = False
        return ok
    finally:
        srv.shutdown()


def main() -> int:
    results = {}
    # off first: if the dialog does not even appear, the rest proves nothing
    results["off"] = run_phase(sweep_on=False)
    results["on"] = run_phase(sweep_on=True)
    verdict = all(results.values())
    print(f"===== blocker_sweep_check verdict: {'PASS' if verdict else 'FAIL'} "
          f"(phases={results}) =====", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
