"""Print what a harvested run recorded: verdict, checks, worker error, log tail.

    python run_info.py <run-id prefix> [...]
Read-only. Paths are joined with os.sep (no backslash literals: this file has
travelled through a heredoc once and lost one)."""
import glob
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HARVEST = "artifacts/windows_mcp_harvest"
for prefix in sys.argv[1:]:
    hits = [h for h in glob.glob(os.path.join(HARVEST, prefix + "*")) if os.path.isdir(h)]
    if not hits:
        print("==", prefix, "not harvested")
        continue
    d = hits[0] + os.sep
    try:
        r = json.load(open(d + "result.json", encoding="utf-8-sig"))
    except OSError:
        print("==", prefix, "no result.json")
        continue
    print("==", os.path.basename(d.rstrip(os.sep))[:8], r.get("scenario") or "", r.get("release_verdict"),
          r.get("reasons"), r.get("execution_status"), r.get("runtime_status"), "verified_pass", r.get("verified_pass"))
    for name, c in (r.get("checks") or {}).items():
        print("   ", name, json.dumps(c, ensure_ascii=False)[:600])
    try:
        w = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
        print("    worker error:", w.get("error"), "| steps:", len(w.get("script_steps") or []), "| app_closed", w.get("app_closed"))
    except OSError:
        pass
    try:
        log = open(d + "native_worker.log", encoding="utf-8", errors="replace").read()
        i = log.find("Traceback")
        print("    log:", (log[i:i + 1200] if i >= 0 else log[-500:]).strip()[:1200])
    except OSError:
        pass
