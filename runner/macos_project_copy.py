"""Run the fixed layer-height project-copy case in a Mac's inactive test login.

Goals: layer (Quality layer-height edit), walls (Strength wall-loops 2->3),
pan (canvas +10 mm global-X object move). All goals edit a named copy, save,
reopen it in a new process and slice; the host verifies independently."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.agent_layer_verify import analyze_gcode
from harness.gcode_check import config_value_all
from harness.pilot_common import inspect_preserved_settings  # noqa: F401 - Windows-track oracle, kept for reference
from harness.pilot_transform import verify_translation
from harness.profile import MINIMAL_CONF, write_conf
from harness.project_3mf import inspect_project
from harness.model_move_pilot import mesh_3mf, source_models, transform_point

SPHERE_SHA256 = "f5f83d00545522c7cde44c0cd4260c325418707afdc83e6056390a0b8800d13c"
COPY_NAMES = {"sphere254": "sphere-254-copy.3mf", "layer": "layer-024-copy.3mf", "walls": "wall-3-copy.3mf", "pan": "pan-x10-copy.3mf"}


def settings_of(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return json.loads(archive.read("Metadata/project_settings.config"))


def sphere_geometry_unchanged(saved, original):
    """Orca retains this fixture's indexed facets but recenters its local mesh."""
    def geometry(raw):
        points, faces, build = mesh_3mf(source_models(raw), lambda: False)
        matrix = tuple(map(float, build))
        return [transform_point(p, matrix) for p in points], faces

    a, a_faces = geometry(saved)
    b, b_faces = geometry(original)
    return (a_faces == b_faces and len(a) == len(b)
            and all(abs(x - y) <= 0.00001 for p, q in zip(a, b) for x, y in zip(p, q)))


def payload(output, run_id, fixture, edit_height, goal, copy_name, pan_presses):
    config = {**MINIMAL_CONF, "app": dict(MINIMAL_CONF["app"])}
    for key in ("orca_upgrade_url", "profile_upgrade_url", "flutter_upgrade_url"):
        config["app"][key] = "http://127.0.0.1:1/version.json"
    seed = output / "seed.conf"
    write_conf(seed, config)
    files = {"reference.3mf": fixture, "run-id": run_id.encode(), "seed.conf": seed.read_bytes(),
             "edit-height": edit_height.encode(), "goal": goal.encode(), "copy-name": copy_name.encode(),
             "pan-presses": str(pan_presses).encode()}
    for filename in ("project_copy.py", "accessibility.py", "ocr.swift"):
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


def verify_walls_differential(saved_raw, fixture_raw, sut):
    """Walls oracle for this SUT build: differential against a committed control.

    The 2.4.1 bundle rewrites the 2.3.6 fixture's config schema on every Save
    Project (version bump, new keys, vector migrations, preset rename, refreshed
    template gcode) - noise that is edit-independent, proven by control run
    control_save4_a5 (probe17: one unrelated edit, identical noise key-for-key
    to run ffe0c6e4). Every difference the judged save makes must therefore be
    either wall_loops 2->3 (plus its dirty-manifest entry) or a difference the
    control made with the exact same value.
    """
    name = "walls_control_242" if sut["version"] == "2.4.2" else "walls_control"
    directory = ROOT / "runner" / "macos"
    meta = json.loads((directory / (name + ".json")).read_text())
    control_raw = (directory / (name + ".3mf")).read_bytes()
    if hashlib.sha256(control_raw).hexdigest() != meta["control_saved_sha256"]:
        raise ValueError("Committed walls control baseline digest mismatch")
    if (meta["sut"]["version"], meta["sut"]["executable_sha256"]) \
            != (sut["version"], sut["executable_sha256"]):
        raise ValueError("Walls control baseline was recorded on a different Orca build")
    control_edit_key = meta["control_edit"]["key"]
    saved = settings_of(saved_raw)
    control = settings_of(control_raw)
    expected = settings_of(fixture_raw)
    if expected.get("wall_loops") != "2" or saved.get("wall_loops") != "3":
        raise ValueError("pilot_wall_loops_target")
    for key in set(saved) - set(expected):
        if key not in control or saved[key] != control[key]:
            raise ValueError(f"mac_walls_unknown_addition:{key}")
    for key, before in expected.items():
        after = saved[key]
        if key == "wall_loops":
            continue  # checked above
        if key == "different_settings_to_system":
            before_keys = set(str(before[0]).split(";")) if before else set()
            after_keys = set(str(after[0]).split(";")) if after else set()
            if not before_keys <= after_keys <= before_keys | {"wall_loops"}:
                raise ValueError("pilot_dirty_manifest_out_of_scope")
            continue
        if after == before:
            continue
        if key != control_edit_key and key in control and after == control[key]:
            continue  # edit-independent migration, proven by the control
        raise ValueError(f"mac_walls_unrelated_setting_changed:{key}")


def verify_plate(output, name, receipt, expected_pid, project_sha256, height, count, *, sphere=False):
    path = output / (name + ".gcode")
    raw = path.read_bytes()
    if (receipt["pid"] != expected_pid or receipt["size"] != len(raw)
            or receipt["sha256"] != hashlib.sha256(raw).hexdigest()
            or receipt["project_sha256"] != project_sha256 or receipt["source"] != "open_process_plate"
            or receipt["export_enabled_before"] is not False or receipt["export_enabled_after"] is not True):
        raise ValueError(f"{name} plate lineage or transfer mismatch")
    facts = (analyze_gcode(raw, layer_height=height, first_layer_height="0.25", expected_height_mm=Decimal(20), allow_startup_retract=True)
             if sphere else analyze_gcode(raw, layer_height=height, allow_startup_retract=True))
    if facts["layer_count"] != count:
        raise ValueError(f"{name} yielded {facts['layer_count']} model layers, expected {count}")
    return {**facts, "artifact": path.name, "origin": "gui_plate_temporary"}


def run(args):
    run_id = uuid.uuid4().hex
    output = ROOT / "artifacts" / "mac_project_copy" / run_id
    output.mkdir(parents=True)
    control = args.wrong_layer_control
    goal = args.goal
    copy_name = COPY_NAMES[goal]
    if control and goal != "layer":
        print("--wrong-layer-control only applies to the layer goal", file=sys.stderr)
        return 2
    summary = {"run_id": run_id, "verdict": "NON_GREEN", "candidate": args.candidate, "goal": goal,
               "test_kind": "wrong_layer_control" if control else f"{goal}_comparison",
               "started_at": datetime.now(timezone.utc).isoformat(), "slices": {},
               "native_save_as": "NOT_TESTED", "gui_gcode_export": "NOT_TESTED"}
    stage = "host.fixture"
    print(f"Evidence: {output}", flush=True)
    try:
        sphere = goal == "sphere254"
        fixture = (ROOT / ("fixtures/feishu_std_sphere.3mf" if sphere else LAYER_FIXTURE)).read_bytes()
        fixture_sha = SPHERE_SHA256 if sphere else LAYER_FIXTURE_SHA256
        if hashlib.sha256(fixture).hexdigest() != fixture_sha:
            raise ValueError("Repository fixture digest mismatch")
        stage = "transport"
        result = subprocess.run(ssh_command(args),
                                input=payload(output, run_id, fixture, "0.32" if control else "0.24",
                                              goal, copy_name, args.pan_presses),
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
            (output / copy_name).write_bytes(data)
        if report.get("ok") is not True:
            stage = report.get("failure_stage") or "guest"
            raise RuntimeError(report.get("error", "Mac worker did not complete"))
        stage = "verify.identity"
        if report["run_id"] != run_id or report["cleanup_verified"] is not True:
            raise ValueError("Run identity or cleanup evidence mismatch")
        if (report["source_before"], report["source_after"]) != (fixture_sha, fixture_sha):
            raise ValueError("Mac original fixture mismatch")
        sut = report["sut"]
        if not sut["version"] or not sut["build"] or not re.fullmatch("[0-9a-f]{64}", sut["executable_sha256"]):
            raise ValueError("Actual Orca build identity is incomplete")
        phases = report["phases"]
        baseline, edit, reopened = phases["baseline"], phases["edit"], phases["reopen"]
        initial = ["0.2", "0.25"] if sphere else ["0.4", "0.4"]
        if (len({baseline["pid"], edit["pid"], reopened["pid"]}) != 3
                or baseline["layers"] != initial or edit["window"] != Path(copy_name).stem
                or reopened["window"] != edit["window"] or edit["layers"] != initial):
            raise ValueError("Missing independent GUI reopen evidence")
        stage = "verify.baseline_slice"
        receipts = report["slice_receipts"]
        if receipts["baseline"]["phase"] != "baseline":
            raise ValueError("Unexpected baseline receipt phase")
        summary["slices"]["baseline"] = verify_plate(
            output, "baseline", receipts["baseline"], baseline["pid"], fixture_sha,
            "0.2" if sphere else "0.4", 100 if sphere else 68, sphere=sphere)
        stage = "verify.saved_project"
        if "project" not in reply:
            raise ValueError("Mac did not return the saved project")
        if hashlib.sha256(data).hexdigest() != report["saved_sha256"]:
            raise ValueError("Recovered project digest mismatch")
        if goal == "layer":
            try:
                oracle = inspect_project(data, fixture, layer_height="0.24")
            except ValueError as error:
                raise ValueError(f"{error}; expected regular/first layers ['0.24', '0.4'], "
                                 f"reopened GUI read {reopened['layers']}") from error
            summary["project"] = oracle
            stage = "verify.reopened_fields"
            if reopened["layers"] != ["0.24", "0.4"]:
                raise ValueError(f"Reopened layer fields mismatch: {reopened['layers']}")
        elif sphere:
            if (report["off_target_layers"] != ["0.24", "0.3"] or report["target_layers"] != initial
                    or reopened["layers"] != initial):
                raise ValueError("Missing sphere height edit and independent readback")
            settings = settings_of(data)
            original = settings_of(fixture)
            for key in ("layer_height", "initial_layer_print_height", "nozzle_diameter", "filament_type",
                        "printer_model", "printer_variant", "print_settings_id"):
                if settings[key] != original[key]:
                    raise ValueError(f"Sphere settings mismatch: {key}")
            if not sphere_geometry_unchanged(data, fixture):
                raise ValueError("Sphere mesh or transform changed")
            summary["project"] = {"sphere_unchanged": True, "layers": initial}
        elif goal == "walls":
            verify_walls_differential(data, fixture, sut)
            summary["project"] = {**inspect_project(data, fixture, layer_height="0.4"), "wall_loops": "3",
                                  "preserved_settings": "differential vs committed control: only wall_loops 2->3"}
            stage = "verify.reopened_fields"
            walls_seen = [baseline.get("wall"), edit.get("wall"), reopened.get("wall")]
            if walls_seen != ["2", "3", "3"]:
                raise ValueError(f"Wall readback mismatch across baseline/edit/reopen: {walls_seen}")
        stage = "verify.edited_slice"
        if receipts["edited"]["phase"] != "reopen":
            raise ValueError("Unexpected edited receipt phase")
        summary["slices"]["edited"] = verify_plate(
            output, "edited", receipts["edited"], reopened["pid"], report["saved_sha256"],
            "0.2" if sphere else ("0.24" if goal == "layer" else "0.4"),
            100 if sphere else (112 if goal == "layer" else 68), sphere=sphere)
        if sphere:
            for key in ("layer_count", "first_z", "last_z", "layer_height"):
                if summary["slices"]["baseline"][key] != summary["slices"]["edited"][key]:
                    raise ValueError(f"Sphere baseline comparison failed: {key}")
        if goal == "walls":
            echoes = config_value_all((output / "edited.gcode").read_bytes(), "wall_loops")
            summary["wall_loops_gcode_echo"] = echoes if echoes else "absent"
            if echoes and set(echoes) != {"3"}:
                raise ValueError(f"Edited gcode wall_loops echo mismatch: {echoes}")
            summary["walls_xy_moves"] = {"baseline": summary["slices"]["baseline"]["positive_xy_e_moves"],
                                         "edited": summary["slices"]["edited"]["positive_xy_e_moves"]}
        if goal == "pan":
            stage = "verify.translation"
            summary["project"] = verify_translation(data, fixture, (output / "edited.gcode").read_bytes(),
                                                    axis="x", distance=10, cancelled=lambda: False)
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
    parser.add_argument("--goal", choices=COPY_NAMES, default="layer",
                        help="Business goal to run (default: the layer-height pilot)")
    parser.add_argument("--pan-presses", type=int, default=10,
                        help="Right-arrow presses for the pan goal (arrow nudge step is measured, not assumed)")
    parser.add_argument("--wrong-layer-control", action="store_true",
                        help="Enter 0.32 in the GUI; the unchanged 0.24 acceptance check must reject it")
    sys.exit(run(parser.parse_args()))
