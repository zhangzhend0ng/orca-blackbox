#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""perf_attach.py — standalone metric sampler, no launcher/AppSession needed.

For probes and manual runs: watch processes by exe name (e.g. the app during
a hand-driven repro) and write the same jsonl schema as the launcher hook.

  python -B tools/perf_attach.py --name snapmaker-orca --seconds 60
  python -B tools/perf_attach.py --pid 1234 --interval 0.2 --out artifacts/perf/repro.jsonl
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import perf_monitor as pm  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", action="append", default=None,
                    help="target exe name/stem (repeatable; default snapmaker-orca)")
    ap.add_argument("--pid", type=int, default=None, help="anchor pid")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--out", default=None, help="output jsonl (default auto)")
    args = ap.parse_args()
    names = args.name or ["snapmaker-orca"]

    out = Path(args.out) if args.out else pm.resolve_out_path(
        names[0].removesuffix(".exe") + "__attach")
    mon = pm.PerfMonitor(targets=names, anchor_pid=args.pid,
                         out_path=out, interval_s=args.interval,
                         use_psutil=True)
    mon.start()
    print(f"[perf-attach] {out} (Ctrl+C to stop early)", file=sys.stderr)
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    summary = mon.stop()
    pids = summary.get("pids", {})
    print(f"[perf-attach] stopped: {len(pids)} pid(s), samples="
          f"{sum(p.get('samples', 0) for p in pids.values())}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
