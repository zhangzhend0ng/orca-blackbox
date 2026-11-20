"""Run the fixed layer-height project-copy case in a Mac's inactive test login."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.profile import MINIMAL_CONF, write_conf
from harness.project_3mf import inspect_project


def payload(output, run_id, fixture):
    config = {**MINIMAL_CONF, "app": dict(MINIMAL_CONF["app"])}
    for key in ("orca_upgrade_url", "profile_upgrade_url", "flutter_upgrade_url"):
        config["app"][key] = "http://127.0.0.1:1/version.json"
    seed = output / "seed.conf"
    write_conf(seed, config)
    files = {"reference.3mf": fixture, "run-id": run_id.encode(), "seed.conf": seed.read_bytes()}
    for filename in ("project_copy.py", "accessibility.py"):
        files[filename] = (ROOT / "runner" / "macos" / filename).read_bytes()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.mode = 0o600
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    return buffer.getvalue()


def ssh_command(args):
    ssh = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
    if args.ssh_config:
        ssh.extend(["-F", str(args.ssh_config)])
    if args.identity:
        ssh.extend(["-i", str(args.identity), "-o", "IdentitiesOnly=yes"])
    if args.known_hosts:
        ssh.extend(["-o", f'UserKnownHostsFile="{args.known_hosts.resolve().as_posix()}"'])
    # Target and credentials stay on the host. No arguments from the caller go into the remote shell command.
    stage = ('umask 077 && work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/orca-bb-copy.XXXXXXXX") '
             '&& cd "$work" && /usr/bin/tar -xzf - && /usr/bin/python3 -B project_copy.py --supervise')
    return [*ssh, "--", args.target, stage]


def run(args):
    run_id = uuid.uuid4().hex
    output = ROOT / "artifacts" / "mac_project_copy" / run_id
    output.mkdir(parents=True)
    summary = {"run_id": run_id, "verdict": "NON_GREEN",
               "native_save_as": "NOT_TESTED", "gui_gcode_export": "NOT_TESTED"}
    print(f"Evidence: {output}", flush=True)
    try:
        fixture = (ROOT / LAYER_FIXTURE).read_bytes()
        if hashlib.sha256(fixture).hexdigest() != LAYER_FIXTURE_SHA256:
            raise ValueError("Repository fixture digest mismatch")
        result = subprocess.run(ssh_command(args), input=payload(output, run_id, fixture),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=345)
        (output / "ssh.log").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"SSH or Mac supervisor exited with {result.returncode}. See ssh.log")
        reply = json.loads(result.stdout)
        report = reply["report"]
        summary["guest"] = report
        (output / "worker.log").write_text(reply["log"], encoding="utf-8")
        if "project" in reply:
            data = base64.b64decode(reply["project"], validate=True)
            (output / "layer-024-copy.3mf").write_bytes(data)
        if not report.get("ok"):
            raise RuntimeError(report.get("error", "Mac worker did not complete"))
        if report["run_id"] != run_id or report["cleanup_verified"] is not True:
            raise ValueError("Run identity or cleanup evidence mismatch")
        if (report["source_before"], report["source_after"]) != (LAYER_FIXTURE_SHA256, LAYER_FIXTURE_SHA256):
            raise ValueError("Mac original fixture mismatch")
        edit, reopened = (report["phases"][key] for key in ("edit", "reopen"))
        if (edit["pid"] == reopened["pid"] or edit["window"] != "layer-024-copy"
                or reopened["window"] != edit["window"] or edit["layers"] != ["0.4", "0.4"]
                or reopened["layers"] != ["0.24", "0.4"]):
            raise ValueError("Missing independent GUI reopen evidence")
        if "project" not in reply:
            raise ValueError("Mac did not return the saved project")
        oracle = inspect_project(data, fixture, layer_height="0.24")
        if oracle["sha256"] != report["saved_sha256"]:
            raise ValueError("Recovered project digest mismatch")
        summary.update(verdict="SHADOW", project=oracle)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        summary["error"] = str(error)
        print(error, file=sys.stderr)
    finally:
        (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(summary["verdict"], flush=True)
    return 0 if summary["verdict"] == "SHADOW" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="OpenSSH destination for the Mac test login (user@host or an SSH alias)")
    parser.add_argument("--ssh-config", type=Path, help="Optional OpenSSH configuration")
    parser.add_argument("--identity", type=Path, help="Optional SSH identity file")
    parser.add_argument("--known-hosts", type=Path, help="Optional pinned SSH known_hosts file")
    sys.exit(run(parser.parse_args()))
