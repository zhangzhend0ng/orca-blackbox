#!/usr/bin/env python3
# m0_boot_check.py — Phase 0 milestone: prove the black-box bootstrap.
# feishu: none  (无基线表映射)
#
#   seed profile -> launch the real exe (visible, no test-mode env) ->
#   find the main window -> preflight env -> capture screenshots over time ->
#   close gracefully.
#
# Artifacts under artifacts/m0/: startup captures (BMP) + report. These
# captures are ALSO the raw material for cutting template images
# (resource/image/) — run with --grab to dump a steady-state shot for that.

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import env_check, launcher, profile, winutil  # noqa: E402


def prepare_output(output_dir=None):
    """Explicit run-owned output must be empty; legacy output remains reusable."""
    out_dir = Path(output_dir).resolve() if output_dir is not None else HERE / "artifacts" / "m0"
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_dir is not None and any(out_dir.iterdir()):
        raise ValueError("m0: run-owned output directory must be empty")
    return out_dir


def write_capture_report(out_dir, evidence, *, exclusive=False):
    """Record bounded bootstrap observations; this is not a PASS verdict."""
    with (Path(out_dir) / "report.json").open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(evidence, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
        stream.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None, help="app exe (default: main checkout Release build)")
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=None, help="optional 3mf/stl to auto-load")
    ap.add_argument("--fresh", action="store_true", help="re-seed the datadir from scratch")
    ap.add_argument("--grab", action="store_true", help="steady-state capture for template cutting")
    ap.add_argument("--keep", action="store_true", help="leave the app running (manual inspection)")
    ap.add_argument("--output-dir", default=None, type=Path,
                    help="empty run-owned directory for captures, report and archive")
    args = ap.parse_args()

    if args.output_dir is not None and (args.fresh or args.datadir.exists()):
        ap.error("run-owned output requires a new datadir and forbids --fresh global cleanup")
    out_dir = prepare_output(args.output_dir)

    profile.seed_profile(args.datadir, fresh=args.fresh)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    evidence = {"schema_version": 1, "case_id": "m0_boot_check", "driver_pid": os.getpid(),
                "app_pid": session.pid, "hwnd": int(session.hwnd),
                "phases": ["launched"], "captures": [], "grab": args.grab, "keep": args.keep}
    _arch = None
    try:
        print(f"[m0-evidence] launched driver_pid={evidence['driver_pid']} app_pid={session.pid} hwnd={int(session.hwnd)}")
        from harness import shot_archive   # same all-cases video trail as boot_session
        archive_kwargs = {"out_root": out_dir / "shots"} if args.output_dir is not None else {}
        _arch = shot_archive.start_archiver(session, Path(sys.argv[0]).stem, **archive_kwargs)
        shot_archive.hook_stdout_tee(_arch)
        report = env_check.print_preflight(session.hwnd)
        evidence["phases"].append("preflight")

        # Capture a few startup phases; PrintWindow(PW_RENDERFULLCONTENT)
        # should include the GL canvas — a black 3D area would mean the
        # (c) experiment failed (see README hazard matrix).
        stamps = [0.5, 2.0, 5.0]
        if args.grab:
            time.sleep(3.0)  # let first paint / preset load settle
            stamps = [0.2]
        for i, wait in enumerate(stamps):
            time.sleep(wait)
            try:
                cap = winutil.capture_window(session.hwnd)
                path = out_dir / ("grab.png" if args.grab else f"startup_{i}.bmp")
                winutil.save_capture_bmp(str(path), cap)
                evidence["captures"].append({"filename": path.name, "width": cap[0], "height": cap[1]})
                print(f"[m0] capture {i}: {cap[0]}x{cap[1]} -> {path.name}")
            except winutil.CaptureError as e:
                print(f"[m0] capture {i} FAILED: {e}")
                return 2

        evidence["phases"].append("captures_complete")
        if args.keep:
            print(f"[m0] --keep: app running (pid {session.pid}); press Ctrl+C to exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        print("[m0] OK" if not report.get("remote_control") else
              "[m0] OK (remote-control layer active: message-injection path required)")
        return 0
    finally:
        evidence["phases"].append("close_requested")
        try:
            session.close()
            evidence["phases"].append("closed")
            print("[m0] app closed")
        finally:
            if _arch is not None:
                _arch.set()
            write_capture_report(out_dir, evidence, exclusive=args.output_dir is not None)


if __name__ == "__main__":
    raise SystemExit(main())
