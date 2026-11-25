#!/usr/bin/env python3
# diag_step_cli_import.py - Feishu #229 first look: what the product's command line makes of a three-solid STEP.
# feishu: none  (#229 first look: a command-line control, not a File > Import action)
"""Runs the product's command line on fixtures/assembly.step and keeps the 3MF it writes.

The file holds three 10 mm cubes in red, green and blue (tools/make_assembly_step.py). Before a
GUI case is written for Feishu #229 this records what the STEP importer produced: how many
objects and parts the saved 3MF holds, how many triangles each has, where each sits, and which
extruder and colours the project names. The command line is not the File > Import menu, so
nothing here is a verdict; the results only say whether the control itself ran.

    & runner/hv_go.ps1 -Cases diag_step_cli_import -NoSync
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
sys.path.insert(0, str(HERE / "tests" / "engine"))

import m7_common as m7  # noqa: E402
from harness import launcher  # noqa: E402
from m3_common import add_common_args  # noqa: E402

FIXTURE = HERE / "fixtures" / "assembly.step"
LOG = "[diag229]"


def read_project(path):
    """Objects, parts and named extruders of the 3MF, straight from its XML."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        # Snapmaker Orca 2.4.0 writes the objects under 3D/Objects/*.model; 3D/3dmodel.model may be empty.
        members = sorted(name for name in names if name.startswith("3D/") and name.endswith(".model"))
        objects, build = [], []
        for member in members:
            model = ET.fromstring(archive.read(member))
            for obj in (e for e in model.iter() if e.tag.rsplit("}", 1)[-1] == "object"):
                entry = {"member": member, "id": obj.get("id"), "type": obj.get("type"), "name": obj.get("name")}
                mesh = obj.find("{*}mesh")
                if mesh is not None:
                    points = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                              for v in mesh.findall("{*}vertices/{*}vertex")]
                    entry["triangles"] = len(mesh.findall("{*}triangles/{*}triangle"))
                    entry["box_mm"] = ([[min(p[a] for p in points), max(p[a] for p in points)] for a in range(3)]
                                       if points else None)
                components = obj.find("{*}components")
                if components is not None:
                    entry["components"] = [{"object": c.get("objectid"), "transform": c.get("transform")}
                                           for c in components]
                objects.append(entry)
            # ElementTree.iter takes "{namespace}*" but not "{*}tag"; the local names are compared by hand.
            build.extend({"member": member, "object": item.get("objectid"), "transform": item.get("transform")}
                         for item in (e for e in model.iter() if e.tag.rsplit("}", 1)[-1] == "item"))
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8-sig"))
        extruders = []
        if "Metadata/model_settings.config" in names:
            meta = ET.fromstring(archive.read("Metadata/model_settings.config"))
            for part in (e for e in meta.iter() if e.tag.rsplit("}", 1)[-1] in ("object", "part")):
                facts = {m.get("key"): m.get("value") for m in part.findall("{*}metadata")}
                extruders.append({"name": part.get("name"), **{k: facts.get(k) for k in ("extruder", "source_file")}})
    return {"model_members": members, "objects": objects, "build": build, "object_extruders": extruders,
            "filament_colour": settings.get("filament_colour"), "filament_ids": settings.get("filament_settings_id")}


def main():
    args = add_common_args(argparse.ArgumentParser()).parse_args()
    root = args.datadir.resolve().parent / "feishu-object-cases" / "229"
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    analysis = {"case": 229, "results": {}, "timings": {}}
    step, project = work / "assembly.step", work / "assembly.3mf"
    exe = Path(args.exe) if args.exe else launcher.default_exe()
    print(f"{LOG} work directory={work}, executable={exe}", flush=True)
    try:
        shutil.copyfile(FIXTURE, step)
        analysis["fixture"] = {"name": "assembly.step", "bytes": step.stat().st_size}
        started = time.monotonic()
        command = [str(exe), "--datadir", str(work / "profile"), "--export-3mf", str(project), str(step)]
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        analysis["timings"]["command_line"] = {"seconds": round(time.monotonic() - started, 1)}
        output = "\n".join(line for line in (run.stdout + "\n" + run.stderr).splitlines()[-400:])
        (work / "cli.log").write_text(output, encoding="utf-8")
        analysis["exit_code"] = run.returncode
        print(f"{LOG} exit={run.returncode} in {analysis['timings']['command_line']['seconds']} s, "
              f"3MF exists={project.is_file()}", flush=True)
        analysis["results"]["the command line exited 0"] = "PASS" if run.returncode == 0 else f"FAIL ({run.returncode})"
        analysis["results"]["a 3MF was written"] = "PASS" if project.is_file() else "FAIL"
        if project.is_file():
            analysis["project"] = read_project(project)
            analysis["project"]["bytes"] = project.stat().st_size
            print(f"{LOG} project: {json.dumps(analysis['project'], ensure_ascii=False)[:900]}", flush=True)
    except subprocess.TimeoutExpired:
        analysis["results"]["the command line exited 0"] = "FAIL (timeout after 300 s)"
    except (BadZipFile, KeyError, StopIteration, ET.ParseError) as exc:
        analysis["results"]["a 3MF was read"] = f"FAIL ({type(exc).__name__}: {exc})"
        traceback.print_exc()
    (work / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
    return m7.m7_verdict(analysis["results"])


if __name__ == "__main__":
    raise SystemExit(main())
