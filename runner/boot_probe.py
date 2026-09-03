#!/usr/bin/env python3
"""boot_probe.py — one-shot Orca boot POPUP census probe (GUEST).

Evaluation scaffolding for the "launch-time popups" hardening task: answers
"what windows appear over the main frame during a real boot, when, and how
do they look" before any guard code is written. NOT a regression case —
never registered in cases.py, writes nothing inside the sandbox except
artifacts/boot_probe_datadir (gitignored).

Phases (one fresh app boot each, config knob = seed conf override):
  a  baseline      — seed EXACTLY as regression seeds today (MINIMAL_CONF).
                     Ground truth: anything pops right now? (update feeds
                     are reachable from the guest; local build is 2.3.6,
                     feed stable is 2.3.6 today — equality is the current
                     luck, see GUI_App::check_new_version_sf).
  b  version-gap   — seed + orca_upgrade_url -> localhost feed claiming
                     9.9.9 (non-force). Reproduces the "Snapmaker releases
                     2.3.7 tomorrow" scenario deterministically.
  f  force-upgrade — localhost feed claiming 9.9.9 + is_force_upgrade=true.
                     Reproduces the modal DownloadDialog that CLOSES THE APP
                     on any button (GUI_App.cpp EVT_ENTER_FORCE_UPGRADE).
  c  conf-fix      — seed with the planned hardening conf (upgrade URLs
                     stubbed to a refused localhost port). Expect zero
                     popups; proves the fix without depending on feed luck.

Observer: 1 Hz sweep of the app pid's VISIBLE top-level windows. Every new
window / title change gets a PrintWindow PNG + OCR + a log line. Main-window
geometry drift is noted without screenshots. App log lines mentioning
update/version/upgrade/sync are tailed for URL + verdict correlation.

Outputs (ASCII-safe where displayed):
  C:\\coil\\boot_probe_report.txt      human summary (ASCII only: safe over GBK relay)
  C:\\coil\\boot_probe_events.json     full event stream (ASCII-escaped UTF-8)
  C:\\coil\\boot_probe_shots\\<phase>\\*.png

Runs under the INTERACTIVE scheduled task 'boot_probe' (PITFALLS 18.7: PS
Direct cannot see the desktop; window enumeration needs the interactive
session) — launch via runner/hv_boot_probe.ps1 (relay-safe, 18.6).

Exit code: 0 = probe completed (findings may be negative), 1 = crashed
before finishing (traceback goes to the report/steps).
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import launcher, profile, winutil  # noqa: E402
from harness.mixing_util import toplevel  # noqa: E402

OUT_REPORT = r"C:\coil\boot_probe_report.txt"
OUT_EVENTS = r"C:\coil\boot_probe_events.json"
SHOTS_DIR = Path(r"C:\coil\boot_probe_shots")

OBSERVE_S = {"a": 180, "b": 150, "f": 90, "c": 150}
STABLE_S = 12.0        # popup confirmed only after it persists this long
POLL_S = 1.0

# Localhost feed used by phases b/f (the app's own http client, in-process,
# so 127.0.0.1 works). Payload mirrors meta-cfg.snapmaker.com exactly.
FEED_PORT = 8891
FEED_BODY_NORMAL = {
    "code": 200, "msg": "",
    "data": {
        "is_full_upgrade": True, "is_force_upgrade": False,
        "version": "9.9.9", "release_type": "stable", "platform_type": "win",
        "full": {
            "default": {
                "file_url": "http://127.0.0.1:1/never_downloaded.exe",
                "file_size": 1, "file_md5": "00", "file_sha256": "00"},
            "file_describe": "boot_probe synthetic 9.9.9 (never a real release)",
        },
    },
}
FEED_BODY_FORCE = dict(FEED_BODY_NORMAL)
FEED_BODY_FORCE["data"] = dict(FEED_BODY_NORMAL["data"])
FEED_BODY_FORCE["data"]["is_force_upgrade"] = True

# Conf overrides per phase (merged over MINIMAL_CONF by seed_profile).
STUB_URL = "http://127.0.0.1:1/version.json"      # connection refused -> silent
PHASE_CONF = {
    "a": {},
    "b": {"orca_upgrade_url": f"http://127.0.0.1:{FEED_PORT}/version.json"},
    "f": {"orca_upgrade_url": f"http://127.0.0.1:{FEED_PORT}/version.json"},
    "c": {"orca_upgrade_url": STUB_URL,
          "profile_upgrade_url": STUB_URL,
          "flutter_upgrade_url": STUB_URL},
}
PHASE_NOTE = {
    "a": "baseline: regression's exact seed today",
    "b": "version-gap sim: feed claims 9.9.9 non-force",
    "f": "force-upgrade sim: feed claims 9.9.9 + is_force_upgrade",
    "c": "conf-fix: upgrade URLs stubbed to refused port",
}


def now_hms() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class StepLog:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def add(self, level: str, step: str, detail: str = "") -> None:
        entry = {"ts": now_hms(), "level": level, "step": step, "detail": detail}
        self.entries.append(entry)
        print(f"[{entry['ts']}] {level} {step} {detail}", flush=True)


LOG = StepLog()


def ascii_safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


# --- localhost feed server (phases b/f) -------------------------------------


class _Feed(BaseHTTPRequestHandler):
    body = FEED_BODY_NORMAL

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        data = json.dumps(self.__class__.body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence the default stderr noise
        pass


def serve_feed(force: bool) -> HTTPServer:
    _Feed.body = FEED_BODY_FORCE if force else FEED_BODY_NORMAL
    srv = HTTPServer(("127.0.0.1", FEED_PORT), _Feed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# --- observer ---------------------------------------------------------------


def snapshot(pid: int) -> dict[int, tuple[str, str, tuple]]:
    """hwnd -> (class, title, rect) for the pid's visible toplevels."""
    out = {}
    for cls, txt, rect, hwnd in toplevel(pid):
        out[hwnd] = (cls, txt, rect)
    return out


def ocr_and_shoot(phase: str, hwnd: int, cls: str, title: str,
                  ev_no: int, t_s: float) -> tuple[str, str]:
    """Save a PrintWindow PNG of the window + OCR it; both best-effort."""
    name = f"{ev_no:03d}_{int(t_s):04d}s_{ascii_safe(cls)}_{ascii_safe(title)[:24]}"
    png = SHOTS_DIR / phase / f"{name}.png"
    text = ""
    try:
        w, h, bgra = winutil.capture_window(hwnd)
        import cv2
        import numpy as np
        img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise OSError("png encode failed")
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(buf.tobytes())
        LOG.add("INFO", "shot", f"{png.name} {w}x{h}")
        from harness import ocr_util
        text = ocr_util.ocr_hwnd(hwnd, scale=2)
    except Exception as exc:  # noqa: BLE001 — capture/OCR are best-effort
        LOG.add("WARN", "shot_failed", f"0x{hwnd:x}: {exc}")
    return str(png), text


def watch(phase: str, session, expect_popup: str | None) -> dict:
    """1 Hz sweep until stable finding or the phase time cap.

    expect_popup: None = assert nothing pops; 'any' = first non-main
    toplevel counts; 'force' = the app may die after the dialog shows.
    """
    pid = session.pid
    main = session.hwnd
    t0 = time.monotonic()
    cap = OBSERVE_S[phase]
    seen: dict[int, tuple[str, str, tuple]] = {}
    events: list[dict] = []
    finding = {"popup": None, "popup_hwnd": None, "popup_since": None,
               "main_rect_first": None, "main_rect_last": None,
               "app_exited": False, "events": events}
    ev_no = 0
    popup_seen_at: float | None = None
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > cap:
            break
        try:
            live = snapshot(pid)
        except Exception as exc:  # noqa: BLE001 — enumeration may race death
            LOG.add("WARN", "snapshot", str(exc))
            live = {}
        if not live and session.alive():
            live = {}
        if not session.alive():
            finding["app_exited"] = True
            LOG.add("WARN", "app_exited", f"t={elapsed:.0f}s")
            break
        if finding["main_rect_first"] is None:
            finding["main_rect_first"] = winutil.window_rect(main)
        finding["main_rect_last"] = winutil.window_rect(main)

        # classify popups: any visible toplevel that is NOT the main frame
        popups = {h: v for h, v in live.items() if h != main}
        if expect_popup and popups and popup_seen_at is None:
            for hwnd, (cls, title, rect) in popups.items():
                ev_no += 1
                png, ocr = ocr_and_shoot(phase, hwnd, cls, title, ev_no, elapsed)
                events.append({"t_s": round(elapsed, 1), "kind": "popup_appear",
                               "hwnd": hex(hwnd), "class": cls,
                               "title": ascii_safe(title), "rect": list(rect),
                               "png": png, "ocr_head": ascii_safe(ocr)[:400]})
                LOG.add("POPUP", "seen",
                        f"0x{hwnd:x} {cls} '{ascii_safe(title)[:60]}' "
                        f"rect={rect} t={elapsed:.0f}s")
            popup_seen_at = time.monotonic()
        if not expect_popup and popups and popup_seen_at is None:
            for hwnd, (cls, title, rect) in popups.items():
                ev_no += 1
                png, ocr = ocr_and_shoot(phase, hwnd, cls, title, ev_no, elapsed)
                events.append({"t_s": round(elapsed, 1), "kind": "unexpected",
                               "hwnd": hex(hwnd), "class": cls,
                               "title": ascii_safe(title), "rect": list(rect),
                               "png": png, "ocr_head": ascii_safe(ocr)[:400]})
                LOG.add("POPUP", "unexpected",
                        f"0x{hwnd:x} {cls} '{ascii_safe(title)[:60]}' "
                        f"rect={rect} t={elapsed:.0f}s")
            popup_seen_at = time.monotonic()

        # title/class drift on a KNOWN popup window (dialog re-titles itself)
        for hwnd, (cls, title, rect) in popups.items():
            old = seen.get(hwnd)
            if old and (old[0] != cls or old[1] != title):
                events.append({"t_s": round(elapsed, 1), "kind": "popup_retitle",
                               "hwnd": hex(hwnd), "old": [old[0], ascii_safe(old[1])],
                               "new": [cls, ascii_safe(title)], "rect": list(rect)})
                LOG.add("INFO", "retitle",
                        f"0x{hwnd:x}: '{ascii_safe(old[1])}' -> "
                        f"'{ascii_safe(title)}' t={elapsed:.0f}s")
        seen = {h: (cls, title, rect) for h, (cls, title, rect) in live.items()}

        # early exit once the expectation is settled
        if expect_popup and popup_seen_at is not None:
            if expect_popup == "force":
                # dialog is up; the app may close on its own only if clicked,
                # which the probe never does — wait a few s then break
                if time.monotonic() - popup_seen_at > 8:
                    finding["popup"] = "force_dialog_seen"
                    break
            elif time.monotonic() - popup_seen_at > STABLE_S:
                finding["popup"] = "seen_stable"
                break
        if not expect_popup and popup_seen_at is not None:
            finding["popup"] = "UNEXPECTED"
            break  # a fix phase must stay clean — no need to keep watching
        time.sleep(POLL_S)
    if expect_popup and popup_seen_at is None and session.alive():
        finding["popup"] = "NOT_SEEN"
    LOG.add("RESULT", "finding", f"phase={phase} popup={finding['popup']} "
                                 f"t={time.monotonic() - t0:.0f}s")
    return finding


def app_log_evidence(datadir: Path) -> list[str]:
    """Newest log under <datadir>/log, lines matching the boot-network
    vocabulary (URLs, versions, sync verdicts) — ASCII-escaped."""
    logdir = datadir / "log"
    if not logdir.exists():
        return ["(no log dir)"]
    cands = sorted(logdir.glob("*.log*"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    if not cands:
        return ["(no log files)"]
    import re
    pat = re.compile(r"update|upgrade|skip_version|new version|updater|sync|"
                     r"wizard|version\.json|meta-cfg|orca_upgrade|data_dir",
                     re.IGNORECASE)
    out = []
    try:
        lines = cands[0].read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001 — log read is best-effort
        return [f"(log read failed: {exc})"]
    for line in lines[-600:]:
        if pat.search(line):
            out.append(ascii_safe(line)[:300])
    return out[-40:] if out else ["(no matching lines in newest log)"]


def run_phase(phase: str, conf_extra: dict) -> dict:
    LOG.add("PHASE", phase, PHASE_NOTE[phase])
    datadir = HERE / "artifacts" / "boot_probe_datadir"
    profile.seed_profile(datadir, fresh=True, conf_extra=conf_extra)
    srv = None
    if phase in ("b", "f"):
        srv = serve_feed(force=(phase == "f"))
        LOG.add("INFO", "feed", f"127.0.0.1:{FEED_PORT} force={phase == 'f'}")
    session = launcher.launch(exe=None, datadir=datadir, wait_window_s=90.0)
    try:
        result = watch(phase, session,
                       expect_popup={"b": "any", "f": "force", "c": None,
                                     "a": None}[phase])
        result["app_log"] = app_log_evidence(datadir)
        result["seed_conf_keys"] = sorted(conf_extra)
        return result
    finally:
        try:
            session.close(timeout_s=15.0)
        except Exception as exc:  # noqa: BLE001 — close is best-effort cleanup
            LOG.add("WARN", "close", str(exc))
        if srv is not None:
            srv.shutdown()


def main() -> int:
    phases = sys.argv[1:] if len(sys.argv) > 1 else ["a", "b", "f", "c"]
    for p in phases:
        if p not in PHASE_CONF:
            print(f"unknown phase {p!r}; use a/b/f/c", flush=True)
            return 1
    try:
        results = {}
        for p in phases:
            results[p] = run_phase(p, PHASE_CONF[p])
        _write_outputs(results)
        return 0
    except Exception:
        LOG.add("FATAL", "crash", traceback.format_exc()[-800:])
        _write_outputs({"crash": {"fatal": LOG.entries[-1]["detail"]}})
        return 1


def _write_outputs(results: dict) -> None:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_EVENTS_PATH = Path(OUT_EVENTS)
    OUT_EVENTS_PATH.write_text(
        json.dumps({"steps": LOG.entries, "phases": results},
                   ensure_ascii=True, indent=1), encoding="utf-8")
    lines = ["boot_probe report (ASCII; guest desktop census)",
             "=" * 60, ""]
    for p, r in results.items():
        if p == "crash":
            lines += ["CRASH:", r.get("fatal", "")[:500], ""]
            continue
        lines += [f"== phase {p}: {PHASE_NOTE[p]}",
                  f"   finding: {r.get('popup')}   app_exited: {r.get('app_exited')}",
                  f"   main rect first: {r.get('main_rect_first')}",
                  f"   main rect last : {r.get('main_rect_last')}"]
        for ev in r.get("events", []):
            lines.append(f"   EVENT t={ev['t_s']}s {ev['kind']}: "
                         f"{ev.get('class')} '{ev.get('title', '')}' "
                         f"rect={ev.get('rect')} png={Path(ev.get('png', '')).name}")
            if ev.get("ocr_head"):
                lines.append(f"      OCR: {ev['ocr_head'][:180]}")
        lines += ["   app-log evidence (tail, filtered):"]
        lines += [f"      {l}" for l in r.get("app_log", [])]
        lines += [""]
    Path(OUT_REPORT).write_text("\n".join(lines), encoding="ascii",
                                errors="replace")
    print(f"\n===== report written: {OUT_REPORT} =====", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
