#!/usr/bin/env python3
"""boot_probe.py — one-shot Orca boot POPUP census probe v2 (GUEST).

Evaluation scaffolding for the "launch-time popups" hardening task: answers
"what windows appear over the main frame during a real boot, when, and how
do they look" before any guard code is written. NOT a regression case —
never registered in cases.py, writes nothing inside the sandbox except
artifacts/boot_probe_datadir (gitignored).

v2 (09-03): census v1 blind spots, fixed after source verification
(AppConfig.cpp / GUI_App.cpp / ReleaseNote.cpp):
  1. v1 conf keys (orca_upgrade_url & co) were written TOP-LEVEL in the
     conf JSON, i.e. as a bogus SECTION. AppConfig::get(key) reads ONLY
     the "app" section (AppConfig.hpp: `get(key)` -> `get("app", key)`),
     so v1's phase b/f silently fell back to the REAL feed URL — no
     localhost fetch, no dialog, exactly what v1 measured. Keys now go
     under {"app": {...}} (profile.conf_extra deep-merges one level).
  2. v1 watcher exited on the FIRST non-main toplevel. The first-run
     Setup Wizard (#32770 'Setup Wizard', self-healing ~10s, measured
     t=2s in phase a) therefore ended phases before any real blocker
     could appear. The watcher now classifies windows (wizard vs
     blockers vs other), tracks the FULL window lifecycle (appear /
     retitle / gone) and only forms findings from NON-wizard windows
     that persist >= STABLE_S.
  3. The app-version dialog actually shown by the boot chain is
     UpdateVersionDialog, titled "New version of Snapmaker Orca"
     (ReleaseNote.cpp) — NOT MsgUpdateSlic3r ("Snapmaker Orca Update",
     dead code in this build). Phases b/f drive it through a localhost
     feed; the feed server now logs every request (fetch proof).
  4. New phase e: refused-port control for b — same app.orca_upgrade_url
     key, port refused. Pairing b (served, dialog?) with e (refused,
     no dialog + app-log fetch-failure lines) proves the conf key is
     read from the app section.

Phases (one fresh app boot each; config knob = seed conf override):
  a  baseline      — seed EXACTLY as regression seeds today (MINIMAL_CONF).
                     Observe: wizard lifecycle + any real blocker (the
                     preset-pack "Configuration update" prompt is NOT
                     conf-stubbable — PresetUpdater derives its feed URL
                     from the country code; see PITFALLS_0901.md 19).
  b  version-gap   — seed + app.orca_upgrade_url -> localhost feed
                     claiming 9.9.9 (non-force). Expect the
                     "New version of Snapmaker Orca" dialog; measures its
                     appearance time and verifies WM_CLOSE keeps the app
                     alive (sweep-title safety for that dialog family).
  f  force-upgrade — localhost feed claiming 9.9.9 + is_force_upgrade=true.
                     Reproduces the modal DownloadDialog that CLOSES THE APP
                     on any button (GUI_App.cpp EVT_ENTER_FORCE_UPGRADE).
  c  conf-fix      — seed with the planned hardening conf: all three
                     upgrade URLs stubbed to a refused localhost port.
                     Expect zero popups from the conf-routable checks.
  e  refused-ctrl  — refused control for b: ONLY app.orca_upgrade_url ->
                     refused port. Same key, no server: the b/e contrast
                     proves whether the key is read (fetch attempt).

Observer: 1 Hz sweep of the app pid's VISIBLE top-level windows. Every new
window / title change gets a PrintWindow PNG + OCR + a log line; every
disappearance gets a lifespan note. Main-window geometry drift is noted
without screenshots. App log lines mentioning update/version/upgrade/sync
are tailed for URL + verdict correlation. t_s is seconds since the watch
start == main-window discovery (+~1s stable margin): the launch sweep
budget (launcher.blocker_sweep_s) must cover it.

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
from dataclasses import dataclass, field
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

OBSERVE_S = {"a": 150, "b": 150, "f": 90, "c": 150, "e": 150}
STABLE_S = 12.0        # popup confirmed only after it persists this long
FORCE_STABLE_S = 8.0   # force dialog: presence is enough, it never self-heals
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
# AppConfig::get(key) reads ONLY the "app" section (AppConfig.hpp) — v1
# wrote these top-level (= bogus section) and the app silently fell back
# to the REAL feed URLs (no fetch, no dialog; the v1 "not proven" gap).
STUB_URL = "http://127.0.0.1:1/version.json"      # connection refused -> silent
PHASE_CONF = {
    "a": {},
    "b": {"app": {"orca_upgrade_url": f"http://127.0.0.1:{FEED_PORT}/version.json"}},
    "f": {"app": {"orca_upgrade_url": f"http://127.0.0.1:{FEED_PORT}/version.json"}},
    "c": {"app": {"orca_upgrade_url": STUB_URL,
                  "profile_upgrade_url": STUB_URL,
                  "flutter_upgrade_url": STUB_URL}},
    "e": {"app": {"orca_upgrade_url": STUB_URL}},  # refused control for b
}
PHASE_NOTE = {
    "a": "baseline: regression's exact seed today (observe wizard + real blockers)",
    "b": "version-gap sim: app.orca_upgrade_url -> localhost feed 9.9.9 non-force",
    "f": "force-upgrade sim: feed claims 9.9.9 + is_force_upgrade",
    "c": "conf-fix: all three upgrade URLs stubbed to refused port",
    "e": "refused control for b: only orca_upgrade_url -> refused port",
}
# Window-title classification (en_US locale pinned by the seeded conf).
# "Snapmaker Orca Update" (MsgUpdateSlic3r) is dead code in this build —
# kept for symmetry with the launcher sweep title list.
WIZARD_TITLE = "setup wizard"


def classify_window(title: str) -> str:
    t = title.strip().lower()
    if t.startswith(WIZARD_TITLE):
        return "wizard"                       # self-healing, never a finding
    if t == "configuration update":
        return "blocker_config"               # MsgUpdateConfig (preset pack)
    if t == "new version of snapmaker orca":
        return "blocker_version"              # UpdateVersionDialog (real)
    if t == "snapmaker orca update":
        return "blocker_version_legacy"       # MsgUpdateSlic3r (dead code)
    return "other"


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
    phase = ""
    requests: list[dict[str, str]] = []

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        data = json.dumps(self.__class__.body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        # fetch proof: every request the app makes at this URL is logged
        req = {"ts": now_hms(), "path": self.path}
        self.__class__.requests.append(req)
        LOG.add("FEED", "get", f"phase={self.__class__.phase} {req['path']}")

    def log_message(self, *args):  # silence the default stderr noise
        pass


def serve_feed(force: bool, phase: str) -> HTTPServer:
    _Feed.body = FEED_BODY_FORCE if force else FEED_BODY_NORMAL
    _Feed.phase = phase
    _Feed.requests = []
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


@dataclass
class WinTrack:
    """Lifecycle state of one observed non-main toplevel window."""
    cls: str
    title: str
    kind: str
    appear_png: str = ""
    first_t: float = 0.0          # monotonic, since watch start
    last_t: float = 0.0
    stable_at: float | None = None  # first t it had persisted >= stable_s
    gone_t: float | None = None
    rect: tuple = ()

    def lifetime(self) -> float | None:
        if self.gone_t is None:
            return None
        return round(self.gone_t - self.first_t, 1)


def watch(phase: str, session, expect: str, stable_s: float = STABLE_S) -> dict:
    """1 Hz sweep until the phase policy settles or the time cap.

    expect:
      'observe' — phase a: watch the full window; list every stable
                  non-wizard popup; never exit early on transient windows.
      'any'     — phase b: the first stable non-wizard popup settles the
                  phase; it is then WM_CLOSEd to prove the dialog family
                  is sweep-safe (WM_CLOSE must not take the app down).
      'force'   — phase f: first stable non-wizard popup = force dialog;
                  a few more seconds, then done (never clicked).
      'clean'   — phases c/e: fix must stay clean; any stable non-wizard
                  popup is a finding, but keep watching to the cap so ALL
                  findings (e.g. the unstubbable preset-pack dialog) list.

    The first-run Setup Wizard (self-healing ~10s) is classified 'wizard':
    never a finding, never ends a phase — only its lifecycle is recorded.
    """
    pid = session.pid
    main = session.hwnd
    t0 = time.monotonic()
    cap = OBSERVE_S[phase]
    events: list[dict] = []
    track: dict[int, WinTrack] = {}
    finding = {"verdict": None, "main_rect_first": None, "main_rect_last": None,
               "app_exited": False, "events": events, "candidates": []}
    ev_no = 0

    def event(kind: str, hwnd: int, extra: dict | None = None) -> dict:
        nonlocal ev_no
        ev_no += 1
        wt = track.get(hwnd)
        rec = {"no": ev_no, "t_s": round(time.monotonic() - t0, 1), "kind": kind,
               "hwnd": hex(hwnd)}
        if wt is not None:
            rec.update({"class": wt.cls, "title": ascii_safe(wt.title),
                        "rect": list(wt.rect) if wt.rect else [],
                        "window_kind": wt.kind})
        if extra:
            rec.update(extra)
        events.append(rec)
        return rec

    while True:
        elapsed = time.monotonic() - t0
        if elapsed > cap:
            break
        try:
            live = snapshot(pid)
        except Exception as exc:  # noqa: BLE001 — enumeration may race death
            LOG.add("WARN", "snapshot", str(exc))
            live = {}
        if not session.alive():
            finding["app_exited"] = True
            LOG.add("WARN", "app_exited", f"t={elapsed:.0f}s")
            break
        if finding["main_rect_first"] is None:
            finding["main_rect_first"] = winutil.window_rect(main)
        finding["main_rect_last"] = winutil.window_rect(main)

        # ---- new / retitled / stable windows --------------------------------
        for hwnd, (cls, title, rect) in live.items():
            if hwnd == main:
                continue
            wt = track.get(hwnd)
            if wt is None:
                wt = WinTrack(cls=cls, title=title, kind=classify_window(title),
                              first_t=elapsed, last_t=elapsed, rect=rect)
                track[hwnd] = wt
                rec = event("window_appear", hwnd)
                if wt.kind != "wizard":  # wizard shot is noise; log only
                    png, ocr = ocr_and_shoot(phase, hwnd, cls, title, ev_no,
                                             elapsed)
                    wt.appear_png = png
                    rec.update({"png": png,
                                "ocr_head": ascii_safe(ocr)[:400]})
                LOG.add("WINDOW" if wt.kind != "wizard" else "WIZARD", "appear",
                        f"0x{hwnd:x} [{wt.kind}] {cls} "
                        f"'{ascii_safe(wt.title)[:60]}' rect={rect} t={elapsed:.0f}s")
            else:
                wt.last_t = elapsed
                wt.rect = rect
                if wt.cls != cls or wt.title != title:
                    rec = event("popup_retitle", hwnd,
                                {"old": [wt.cls, ascii_safe(wt.title)]})
                    LOG.add("INFO", "retitle",
                            f"0x{hwnd:x}: '{ascii_safe(wt.title)}' -> "
                            f"'{ascii_safe(title)}' t={elapsed:.0f}s")
                    wt.cls, wt.title, wt.kind = cls, title, classify_window(title)
                    if wt.kind != "wizard":
                        png, ocr = ocr_and_shoot(phase, hwnd, cls, title,
                                                 ev_no, elapsed)
                        wt.appear_png = png
                        rec.update({"png": png,
                                    "ocr_head": ascii_safe(ocr)[:400]})
            if (wt.stable_at is None and wt.kind != "wizard"
                    and elapsed - wt.first_t >= stable_s):
                wt.stable_at = elapsed
                rec = event("candidate_stable", hwnd,
                            {"png": wt.appear_png})
                finding["candidates"].append(
                    {"t_s": round(elapsed, 1), "kind": wt.kind,
                     "class": wt.cls, "title": ascii_safe(wt.title),
                     "hwnd": hex(hwnd)})
                LOG.add("FINDING", "candidate_stable",
                        f"0x{hwnd:x} [{wt.kind}] '{ascii_safe(wt.title)[:60]}' "
                        f"stable at t={elapsed:.0f}s")

        # ---- gone windows ----------------------------------------------------
        for hwnd, wt in list(track.items()):
            if wt.gone_t is None and hwnd not in live:
                wt.gone_t = elapsed
                rec = event("window_gone", hwnd,
                            {"lifetime_s": wt.lifetime()})
                LOG.add("WIZARD" if wt.kind == "wizard" else "WINDOW", "gone",
                        f"0x{hwnd:x} [{wt.kind}] '{ascii_safe(wt.title)[:60]}' "
                        f"t={elapsed:.0f}s lifetime={wt.lifetime()}s")

        # ---- phase policy ----------------------------------------------------
        stable_hwnds = [h for h, wt in track.items()
                        if wt.kind != "wizard" and wt.stable_at is not None]
        if expect == "force":
            if stable_hwnds:
                # the force dialog is up; the probe never clicks it — the app
                # may stay up (modal) or close itself; wait a few s, then done
                time.sleep(min(3.0, max(0.0, cap - elapsed)))
                finding["verdict"] = "force_dialog_seen"
                break
        elif expect == "any":
            if stable_hwnds:
                finding["verdict"] = "seen_stable"
                finding["close_test"] = close_test(session, stable_hwnds,
                                                   track, t0)
                break
        # 'observe'/'clean': keep watching to the cap (all findings listed)
        time.sleep(POLL_S)

    if expect in ("any", "force") and finding["verdict"] is None \
            and not finding["app_exited"]:
        finding["verdict"] = "not_seen"
    if expect in ("observe", "clean"):
        cands = finding["candidates"]
        finding["verdict"] = "clean" if not cands else \
            "seen:" + ",".join(f"{c['kind']}@{c['t_s']}s" for c in cands)
    if expect == "observe":
        wiz = [wt for wt in track.values() if wt.kind == "wizard"]
        finding["wizard_seen"] = bool(wiz)
        finding["wizard_lifetimes_s"] = [wt.lifetime() for wt in wiz]
    LOG.add("RESULT", "finding", f"phase={phase} verdict={finding['verdict']} "
                                 f"t={time.monotonic() - t0:.0f}s")
    return finding


def close_test(session, hwnds: list[int], track: dict[int, WinTrack],
               t0: float) -> dict:
    """WM_CLOSE the candidate dialogs; verify the app survives.

    Sweep-title safety evidence on a REAL wx dialog: the launcher sweep
    WM_CLOSEs title-matched windows; a family that exits the app on
    WM_CLOSE must never join BLOCKER_TITLES (the force DownloadDialog is
    the known counter-example).
    """
    out = {"attempted": True, "closed": [], "app_alive": None}
    titles = [ascii_safe(track[h].title) for h in hwnds]
    for h in hwnds:
        winutil.close_window(h)
    out["closed"] = [hex(h) for h in hwnds]
    time.sleep(2.0)
    out["app_alive"] = session.alive()
    LOG.add("TEST", "wm_close_real_dialog",
            f"titles={titles} closed={out['closed']} "
            f"app_alive={out['app_alive']} t={time.monotonic() - t0:.0f}s")
    return out


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
                     r"wizard|version\.json|meta-cfg|orca_upgrade|data_dir|"
                     r"http_status|Error getting",
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
    t_seed0 = time.monotonic()
    profile.seed_profile(datadir, fresh=True, conf_extra=conf_extra)
    srv = None
    if phase in ("b", "f"):
        srv = serve_feed(force=(phase == "f"), phase=phase)
        LOG.add("INFO", "feed", f"127.0.0.1:{FEED_PORT} force={phase == 'f'}")
    # census must observe RAW boots — dismiss_blockers would eat the very
    # popups this probe exists to census (launcher sweep, PITFALLS 19)
    session = launcher.launch(exe=None, datadir=datadir, wait_window_s=90.0,
                              dismiss_blockers=False)
    boot_s = round(time.monotonic() - t_seed0, 1)
    LOG.add("INFO", "booted", f"seed+launch took {boot_s}s "
                              f"(watch t=0 == main-window discovery)")
    try:
        expect = {"b": "any", "f": "force", "c": "clean", "e": "clean",
                  "a": "observe"}[phase]
        stable_s = FORCE_STABLE_S if phase == "f" else STABLE_S
        result = watch(phase, session, expect, stable_s=stable_s)
        result["boot_s"] = boot_s
        result["app_log"] = app_log_evidence(datadir)
        result["seed_conf_keys"] = sorted(conf_extra.get("app", {}))
        if phase in ("b", "f"):
            result["feed_requests"] = list(_Feed.requests)
            LOG.add("RESULT", "feed_requests",
                    f"phase={phase} count={len(_Feed.requests)}")
        else:
            result["feed_requests"] = []
        return result
    finally:
        try:
            session.close(timeout_s=15.0)
        except Exception as exc:  # noqa: BLE001 — close is best-effort cleanup
            LOG.add("WARN", "close", str(exc))
        if srv is not None:
            srv.shutdown()
            _Feed.requests = []


def main() -> int:
    phases = sys.argv[1:] if len(sys.argv) > 1 else ["a", "b", "f", "c", "e"]
    for p in phases:
        if p not in PHASE_CONF:
            print(f"unknown phase {p!r}; use a/b/f/c/e", flush=True)
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
    lines = ["boot_probe report v2 (ASCII; guest desktop census)",
             "=" * 60, ""]
    for p, r in results.items():
        if p == "crash":
            lines += ["CRASH:", r.get("fatal", "")[:500], ""]
            continue
        lines += [f"== phase {p}: {PHASE_NOTE[p]}",
                  f"   verdict: {r.get('verdict')}   app_exited: {r.get('app_exited')}",
                  f"   boot_s (seed+launch): {r.get('boot_s')}",
                  f"   main rect first: {r.get('main_rect_first')}",
                  f"   main rect last : {r.get('main_rect_last')}",
                  f"   wizard seen: {r.get('wizard_seen')} "
                  f"lifetimes_s: {r.get('wizard_lifetimes_s')}"]
        for cand in r.get("candidates", []):
            lines.append(f"   CANDIDATE t={cand['t_s']}s [{cand['kind']}] "
                         f"'{ascii_safe(cand['title'])}' "
                         f"class={cand.get('class')}")
        ct = r.get("close_test")
        if ct:
            lines.append(f"   close_test(real dialog): closed={ct.get('closed')} "
                         f"app_alive={ct.get('app_alive')}")
        if r.get("feed_requests"):
            lines.append(f"   feed requests ({len(r['feed_requests'])}): "
                         f"{[q['path'] for q in r['feed_requests']]}")
        lines += ["   events:"]
        for ev in r.get("events", []):
            line = (f"      t={ev['t_s']}s {ev['kind']}: "
                    f"{ev.get('window_kind', '')} {ev.get('class')} "
                    f"'{ev.get('title', '')}'")
            if ev.get("rect"):
                line += f" rect={ev['rect']}"
            line += f" png={Path(ev.get('png', '')).name}"
            if ev.get("lifetime_s"):
                line += f" lifetime={ev['lifetime_s']}s"
            lines.append(line)
            if ev.get("ocr_head"):
                lines.append(f"         OCR: {ev['ocr_head'][:180]}")
        lines += ["   app-log evidence (tail, filtered):"]
        lines += [f"      {l}" for l in r.get("app_log", [])]
        lines += [""]
    Path(OUT_REPORT).write_text("\n".join(lines), encoding="ascii",
                                errors="replace")
    print(f"\n===== report written: {OUT_REPORT} =====", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
