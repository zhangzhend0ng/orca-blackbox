#!/usr/bin/env python3
# make_agent_layer_redblue.py - build fixtures/agent_layer_redblue.3mf from fixtures/agent_layer_cube.3mf.
#
# The only change is the colour of the first two filaments of the project settings:
# extruder 1 red, extruder 2 blue. Feishu #228 imports an OBJ whose faces carry a red and
# a blue material; with the template's own colours (yellow, yellow-green, teal, cream, red)
# the two painted regions would be shown in two yellows. Every other member is copied as it is.
#
#   python tools/make_agent_layer_redblue.py [--check]
#
# --check only reports whether the fixture on disk is what this script would write.
from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "agent_layer_cube.3mf"
TARGET = ROOT / "fixtures" / "agent_layer_redblue.3mf"
COLOURS = ["#FF0000", "#0000FF"]


def build(path: Path) -> None:
    with ZipFile(SOURCE) as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "Metadata/project_settings.config":
                settings = json.loads(data.decode("utf-8-sig"))
                colours = list(settings["filament_colour"])
                colours[:len(COLOURS)] = COLOURS
                settings["filament_colour"] = colours
                data = json.dumps(settings, ensure_ascii=False, indent=2).encode("utf-8")
            target.writestr(info.filename, data)


def colours(path: Path) -> list:
    with ZipFile(path) as archive:
        settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8-sig"))
    return settings["filament_colour"]


def main() -> int:
    if "--check" in sys.argv:
        with ZipFile(SOURCE) as source, ZipFile(TARGET) as target:
            same_members = sorted(source.namelist()) == sorted(target.namelist())
            others = all(source.read(name) == target.read(name) for name in source.namelist()
                         if name != "Metadata/project_settings.config")
        ok = same_members and others and colours(TARGET)[:2] == COLOURS
        print(f"{TARGET.name}: members={same_members} others_unchanged={others} "
              f"filament_colour={colours(TARGET)} -> {'ok' if ok else 'DIFFERS'}")
        return 0 if ok else 1
    build(TARGET)
    print(f"wrote {TARGET} filament_colour={colours(TARGET)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
