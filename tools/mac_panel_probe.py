"""Drive the Orca panel recon probe in the local test login (coilwin, gui/502).

Stages runner/macos/panel_probe.py + accessibility.py + fixture + seed into a
fresh 0700 temp dir, runs it through a one-shot LaunchAgent with the trusted
signed Python.app, then harvests out/*.json into artifacts/mac_probes/.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent_protocol import LAYER_FIXTURE  # noqa: E402
from harness.profile import MINIMAL_CONF, write_conf  # noqa: E402

HARVEST_BASE = ROOT / "artifacts" / "mac_probes" / "2026-11-22"
TRUSTED_PYTHON = Path("/Applications/Xcode.app/Contents/Developer/Library/Frameworks/"
                      "Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python")
STAGE_TIMEOUT = 900


def stage(work, script):
    config = {**MINIMAL_CONF, "app": dict(MINIMAL_CONF["app"])}
    for key in ("orca_upgrade_url", "profile_upgrade_url", "flutter_upgrade_url"):
        config["app"][key] = "http://127.0.0.1:1/version.json"
    seed = work / "seed.conf"
    write_conf(seed, config)
    for name in (script, "accessibility.py"):
        shutil.copy2(ROOT / "runner" / "macos" / name, work / name)
    shutil.copy2(ROOT / LAYER_FIXTURE, work / "probe.3mf")


def main():
    script = sys.argv[1] if len(sys.argv) > 1 else "panel_probe.py"
    harvest_name = sys.argv[2] if len(sys.argv) > 2 else script.replace(".py", "")
    harvest = HARVEST_BASE / harvest_name
    if not TRUSTED_PYTHON.is_file():
        sys.exit("Trusted Python.app not found")
    work = Path(tempfile.mkdtemp(prefix="orca-bb-panel.", dir=tempfile.gettempdir()))
    work.chmod(0o700)
    stage(work, script)
    label = "local.orcabb.panel-probe." + uuid.uuid4().hex[:12]
    logfile = work / "worker.log"
    job = {"Label": label, "LimitLoadToSessionType": "Aqua", "RunAtLoad": True,
           "ProgramArguments": [str(TRUSTED_PYTHON), "-B", "-u", str(work / script)],
           "WorkingDirectory": str(work), "StandardOutPath": str(logfile),
           "StandardErrorPath": str(logfile)}
    plist = work / "probe.plist"
    plist.write_bytes(plistlib.dumps(job))
    result_file = work / "result.json"
    domain = f"gui/{os.getuid()}"
    print(f"work={work} label={label}", flush=True)
    try:
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, timeout=15)
        deadline = time.monotonic() + STAGE_TIMEOUT
        while time.monotonic() < deadline and not result_file.exists():
            time.sleep(2)
    finally:
        subprocess.run(["launchctl", "bootout", domain + "/" + label],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    if not result_file.exists():
        print(f"PROBE_TIMEOUT evidence={work}")
        if logfile.exists():
            print(logfile.read_text(errors="replace")[-4000:])
        return 1
    result = json.loads(result_file.read_text())
    harvest.mkdir(parents=True, exist_ok=True)
    for path in sorted(work.glob("out/*")) + sorted(work.glob("*.3mf")) + [logfile, result_file]:
        if path.is_file():
            shutil.copy2(path, harvest / path.name)
    print(json.dumps(result, indent=1)[:6000])
    print(f"HARVEST={harvest} kept_work={work}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
