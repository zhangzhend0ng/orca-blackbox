#!/usr/bin/env python3
# diag_step_cli_import.py - Feishu #229 first look: what the product's command line makes of a three-solid STEP.
# feishu: none  (#229 first look: command-line controls, not File > Import actions)
"""Runs the product's command line on three inputs and keeps whatever 3MF it writes.

The inputs are a 20 mm STL (written here), the calibration STEP that ships with the product
(read from the build's resources when it is there), and fixtures/assembly.step — three 10 mm
cubes in red, green and blue from tools/make_assembly_step.py. Before a GUI case is written for
Feishu #229 this records what the STEP importer produced: the exit code and output of each
conversion, and for each 3MF the objects and parts it holds, their triangles, positions and
extruders. The command line is not the File > Import menu, so nothing here is a verdict; the
results only say whether the controls ran and were recorded.

    & runner/hv_go.ps1 -Cases diag_step_cli_import -NoSync
"""
import argparse
import json
import struct
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

ASSEMBLY = HERE / "fixtures" / "assembly.step"
LOG = "[diag229]"
TAIL = 60


def write_cube(path, side=20.0):
    """A 12-triangle binary STL cube with one corner at the origin."""
    p = [(x, y, z) for z in (0.0, side) for y in (0.0, side) for x in (0.0, side)]
    faces = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    triangle = struct.Struct("<12fH")
    with path.open("wb") as output:
        output.write(struct.pack("<80sI", b"orca-blackbox #229 control cube", len(faces)))
        for face in faces:
            output.write(triangle.pack(0, 0, 0, *(axis for index in face for axis in p[index]), 0))


def read_project(path):
    """Objects, build items and named extruders of the 3MF, straight from its XML."""
    def local(element):
        return element.tag.rsplit("}", 1)[-1]

    with ZipFile(path) as archive:
        names = archive.namelist()
        # Snapmaker Orca 2.4.0 writes each mesh under 3D/Objects/*.model and the build items in
        # 3D/3dmodel.model. ElementTree.iter takes "{namespace}*" but not "{*}tag": the local
        # names are compared by hand.
        members = sorted(name for name in names if name.startswith("3D/") and name.endswith(".model"))
        objects, build = [], []
        for member in members:
            model = ET.fromstring(archive.read(member))
            for obj in (e for e in model.iter() if local(e) == "object"):
                entry = {"member": member, "id": obj.get("id"), "type": obj.get("type"), "name": obj.get("name")}
                mesh = next((e for e in obj if local(e) == "mesh"), None)
                if mesh is not None:
                    points = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                              for v in (e for e in mesh.iter() if local(e) == "vertex")]
                    entry["triangles"] = sum(1 for e in mesh.iter() if local(e) == "triangle")
                    entry["box_mm"] = ([[min(p[a] for p in points), max(p[a] for p in points)] for a in range(3)]
                                       if points else None)
                components = next((e for e in obj if local(e) == "components"), None)
                if components is not None:
                    entry["components"] = [{"object": c.get("objectid"), "transform": c.get("transform")}
                                           for c in components]
                objects.append(entry)
            build.extend({"member": member, "object": item.get("objectid"), "transform": item.get("transform")}
                         for item in (e for e in model.iter() if local(e) == "item"))
        extruders = []
        if "Metadata/model_settings.config" in names:
            meta = ET.fromstring(archive.read("Metadata/model_settings.config"))
            for part in (e for e in meta.iter() if local(e) in ("object", "part")):
                facts = {m.get("key"): m.get("value") for m in part if local(m) == "metadata"}
                extruders.append({"kind": local(part), "name": part.get("name"),
                                  **{k: facts.get(k) for k in ("extruder", "source_file", "source_object_id",
                                                               "source_volume_id")}})
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8-sig"))
    return {"model_members": members, "objects": objects, "build": build, "object_extruders": extruders,
            "filament_colour": settings.get("filament_colour"), "filament_ids": settings.get("filament_settings_id"),
            "extruder_colour": settings.get("extruder_colour")}


def convert(exe, work, label, source):
    """One command-line conversion; what it printed is kept in full next to its exit code."""
    project = work / f"{label}.3mf"
    started = time.monotonic()
    command = [str(exe), "--datadir", str(work / f"profile-{label}"), "--export-3mf", str(project), str(source)]
    record = {"source": source.name, "source_bytes": source.stat().st_size, "command": command[1:]}
    try:
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        output = "\n".join(line for line in (run.stdout + "\n" + run.stderr).splitlines()[-400:])
        record["exit_code"] = run.returncode
    except subprocess.TimeoutExpired as exc:
        output = f"timeout after {exc.timeout} s"
        record["exit_code"] = "timeout"
    record["seconds"] = round(time.monotonic() - started, 1)
    (work / f"{label}.log").write_text(output, encoding="utf-8")
    record["output_tail"] = output.splitlines()[-TAIL:]
    record["3mf_written"] = project.is_file()
    if project.is_file():
        try:
            record["project"] = read_project(project)
            record["project"]["bytes"] = project.stat().st_size
        except (BadZipFile, KeyError, StopIteration, ET.ParseError, ValueError) as exc:
            record["project_error"] = f"{type(exc).__name__}: {exc}"
    print(f"{LOG} {label}: exit={record['exit_code']} in {record['seconds']} s, 3MF={record['3mf_written']}", flush=True)
    if "project" in record:
        print(f"{LOG} {label} project: {json.dumps(record['project'], ensure_ascii=False)[:1500]}", flush=True)
    for line in record["output_tail"][-25:]:
        print(f"{LOG} {label} | {line[:300]}", flush=True)
    return record


def main():
    args = add_common_args(argparse.ArgumentParser()).parse_args()
    root = args.datadir.resolve().parent / "feishu-object-cases" / "229"
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    analysis = {"case": 229, "results": {}, "controls": {}}
    exe = Path(args.exe) if args.exe else launcher.default_exe()
    print(f"{LOG} work directory={work}, executable={exe}", flush=True)
    try:
        cube = work / "cube_20mm.stl"
        write_cube(cube)
        inputs = [("stl", cube), ("assembly", ASSEMBLY)]
        shipped = exe.parent / "resources" / "calib" / "volumetric_speed" / "SpeedTestStructure.step"
        if shipped.is_file():
            inputs.insert(1, ("shipped_step", shipped))
        else:
            analysis["shipped_step"] = f"not found: {shipped}"
        analysis["executable"] = {"path": str(exe)}
        for label, source in inputs:
            analysis["controls"][label] = convert(exe, work, label, source)
        analysis["results"]["the command-line controls ran and were recorded"] = (
            "PASS" if len(analysis["controls"]) == len(inputs) else "FAIL")
    except Exception as exc:  # noqa: BLE001 - a control keeps whatever happened
        analysis["results"]["the command-line controls ran and were recorded"] = (
            f"FAIL ({type(exc).__name__}: {exc})")
        traceback.print_exc()
    (work / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
    return m7.m7_verdict(analysis["results"])


if __name__ == "__main__":
    raise SystemExit(main())
