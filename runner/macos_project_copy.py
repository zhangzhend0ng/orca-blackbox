"""Run the fixed layer-height project-copy case in a Mac's inactive test login."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.agent_layer_verify import analyze_gcode
from harness.profile import MINIMAL_CONF, write_conf
from harness.project_3mf import inspect_project


def payload(output, run_id, fixture, edit_height):
    config = {**MINIMAL_CONF, "app": dict(MINIMAL_CONF["app"])}
    for key in ("orca_upgrade_url", "profile_upgrade_url", "flutter_upgrade_url"):
        config["app"][key] = "http://127.0.0.1:1/version.json"
    seed = output / "seed.conf"
    write_conf(seed, config)
    files = {"reference.3mf": fixture, "run-id": run_id.encode(), "seed.conf": seed.read_bytes(),
             "edit-height": edit_height.encode()}
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


def verify_plate(output, name, receipt, expected_pid, project_sha256, height, count):
    path = output / (name + ".gcode")
    raw = path.read_bytes()
    if (receipt["pid"] != expected_pid or receipt["size"] != len(raw)
            or receipt["sha256"] != hashlib.sha256(raw).hexdigest()
            or receipt["project_sha256"] != project_sha256 or receipt["source"] != "open_process_plate"
            or receipt["export_enabled_before"] is not False or receipt["export_enabled_after"] is not True):
        raise ValueError(f"{name} plate lineage or transfer mismatch")
    facts = analyze_gcode(raw, layer_height=height)
    if facts["layer_count"] != count:
        raise ValueError(f"{name} yielded {facts['layer_count']} model layers, expected {count}")
    return {**facts, "artifact": path.name, "origin": "gui_plate_temporary"}


def run(args):
    run_id = uuid.uuid4().hex
    output = ROOT / "artifacts" / "mac_project_copy" / run_id
    output.mkdir(parents=True)
    control = args.wrong_layer_control
    summary = {"run_id": run_id, "verdict": "NON_GREEN", "candidate": args.candidate,
               "test_kind": "wrong_layer_control" if control else "layer_comparison",
               "started_at": datetime.now(timezone.utc).isoformat(), "slices": {},
               "native_save_as": "NOT_TESTED", "gui_gcode_export": "NOT_TESTED"}
    stage = "host.fixture"
    print(f"Evidence: {output}", flush=True)
    try:
        fixture = (ROOT / LAYER_FIXTURE).read_bytes()
        if hashlib.sha256(fixture).hexdigest() != LAYER_FIXTURE_SHA256:
            raise ValueError("Repository fixture digest mismatch")
        stage = "transport"
        result = subprocess.run(ssh_command(args), input=payload(output, run_id, fixture, "0.32" if control else "0.24"),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        (output / "ssh.log").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"SSH or Mac supervisor exited with {result.returncode}. See ssh.log")
        reply = json.loads(result.stdout)
        report = reply["report"]
        summary["guest"] = report
        stage = "harvest"
        (output / "worker.log").write_text(reply["log"], encoding="utf-8")
        for name in ("baseline", "edited"):
            if name in reply.get("gcodes", {}):
                raw = base64.b64decode(reply["gcodes"][name], validate=True)
                (output / (name + ".gcode")).write_bytes(raw)
        if "project" in reply:
            data = base64.b64decode(reply["project"], validate=True)
            (output / "layer-024-copy.3mf").write_bytes(data)
        if report.get("ok") is not True:
            stage = report.get("failure_stage") or "guest"
            raise RuntimeError(report.get("error", "Mac worker did not complete"))
        stage = "verify.identity"
        if report["run_id"] != run_id or report["cleanup_verified"] is not True:
            raise ValueError("Run identity or cleanup evidence mismatch")
        if (report["source_before"], report["source_after"]) != (LAYER_FIXTURE_SHA256, LAYER_FIXTURE_SHA256):
            raise ValueError("Mac original fixture mismatch")
        sut = report["sut"]
        if not sut["version"] or not sut["build"] or not re.fullmatch("[0-9a-f]{64}", sut["executable_sha256"]):
            raise ValueError("Actual Orca build identity is incomplete")
        phases = report["phases"]
        baseline, edit, reopened = phases["baseline"], phases["edit"], phases["reopen"]
        if (len({baseline["pid"], edit["pid"], reopened["pid"]}) != 3
                or baseline["layers"] != ["0.4", "0.4"] or edit["window"] != "layer-024-copy"
                or reopened["window"] != edit["window"] or edit["layers"] != ["0.4", "0.4"]):
            raise ValueError("Missing independent GUI reopen evidence")
        stage = "verify.baseline_slice"
        receipts = report["slice_receipts"]
        if receipts["baseline"]["phase"] != "baseline":
            raise ValueError("Unexpected baseline receipt phase")
        summary["slices"]["baseline"] = verify_plate(
            output, "baseline", receipts["baseline"], baseline["pid"], LAYER_FIXTURE_SHA256, "0.4", 68)
        stage = "verify.saved_project"
        if "project" not in reply:
            raise ValueError("Mac did not return the saved project")
        if hashlib.sha256(data).hexdigest() != report["saved_sha256"]:
            raise ValueError("Recovered project digest mismatch")
        try:
            oracle = inspect_project(data, fixture, layer_height="0.24")
        except ValueError as error:
            raise ValueError(f"{error}; expected regular/first layers ['0.24', '0.4'], "
                             f"reopened GUI read {reopened['layers']}") from error
        summary["project"] = oracle
        stage = "verify.reopened_fields"
        if reopened["layers"] != ["0.24", "0.4"]:
            raise ValueError(f"Reopened layer fields mismatch: {reopened['layers']}")
        stage = "verify.edited_slice"
        if receipts["edited"]["phase"] != "reopen":
            raise ValueError("Unexpected edited receipt phase")
        summary["slices"]["edited"] = verify_plate(
            output, "edited", receipts["edited"], reopened["pid"], oracle["sha256"], "0.24", 112)
        if control:
            stage = "control.unexpected_acceptance"
            raise ValueError("Incorrect input was not detected by the independent checks")
        summary["verdict"] = "SHADOW"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary["failure_stage"] = stage
        summary["error"] = str(error)
        print(error, file=sys.stderr)
    finally:
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        pending = output / "result.json.tmp"
        pending.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        os.replace(pending, output / "result.json")
    print(summary["verdict"], flush=True)
    return 0 if summary["verdict"] == "SHADOW" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="OpenSSH destination for the Mac test login (user@host or an SSH alias)")
    parser.add_argument("--ssh-config", type=Path, help="Optional OpenSSH configuration")
    parser.add_argument("--identity", type=Path, help="Optional SSH identity file")
    parser.add_argument("--known-hosts", type=Path, help="Optional pinned SSH known_hosts file")
    parser.add_argument("--candidate", help="Build request label for combining platform reports")
    parser.add_argument("--wrong-layer-control", action="store_true",
                        help="Enter 0.32 in the GUI; the unchanged 0.24 acceptance check must reject it")
    sys.exit(run(parser.parse_args()))
