"""Recompute commanded outer-wall flow for the fixed U1/T0 #276 export."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time


def inspect(path, excerpt=False):
    data = path.read_bytes()
    source = data.decode("utf-8").splitlines()
    if excerpt:
        rows = [(int(number), line) for row in source if not row.startswith("#")
                for number, _, line in [row.partition(": ")]]
    else:
        rows = list(enumerate(source, 1))
    settings = dict(line[2:].split(" = ", 1) for _, line in rows
                    if line.startswith("; ") and " = " in line)
    diameter = float(settings["filament_diameter"].split(",")[0])
    filament_area = math.pi * (diameter / 2) ** 2
    width = float(settings["outer_wall_line_width"])
    height = float(settings["layer_height"])
    ratio = float(settings["filament_flow_ratio"].split(",")[0])
    cap = float(settings["filament_max_volumetric_speed"].split(",")[0])
    rounded_area = height * (width - height * (1 - math.pi / 4)) * ratio
    x = y = feed = tool = None
    absolute_xy = excerpt  # The numbered excerpt starts after the export's G90.
    relative_e = wiping = outer = False
    layers = []
    moves = []
    for number, raw in rows:
        if raw.startswith(";Z:"):
            layers.append(float(raw[3:]))
        elif raw.startswith(";TYPE:"):
            outer = raw == ";TYPE:Outer wall"
        elif raw in {";WIPE_START", ";WIPE_END"}:
            wiping = raw == ";WIPE_START"
        if raw == "; CONFIG_BLOCK_START":
            break
        op, _, arguments = raw.partition(";")[0].strip().partition(" ")
        if op in {"M82", "M83"}:
            relative_e = op == "M83"
        elif op in {"G90", "G91"}:
            absolute_xy = op == "G90"
        elif re.fullmatch(r"T\d+", op):
            tool = int(op[1:])
        if op not in {"G0", "G1", "G2", "G3", "G92"}:
            continue
        args = {key: float(value) for key, value in
                re.findall(r"([XYEF])(-?(?:\d+(?:\.\d+)?|\.\d+))", arguments)}
        if op == "G92":
            if "X" in args or "Y" in args:
                raise ValueError(f"Unexpected XY coordinate reset at {number}")
            continue
        if not absolute_xy and ("X" in args or "Y" in args):
            raise ValueError(f"Unexpected relative XY move at {number}")
        nx, ny = args.get("X", x), args.get("Y", y)
        feed = args.get("F", feed)
        if (layers and outer and not wiping and args.get("E", 0) > 0
                and (x, y) != (nx, ny)):
            if not (op in {"G0", "G1"} and relative_e and tool == 0 and feed
                    and None not in (x, y, nx, ny)):
                raise ValueError(f"Unexpected outer-wall deposition format at {number}")
            if excerpt or len(layers) > 1:
                dx, dy = nx - x, ny - y
                length = math.hypot(dx, dy)
                speed = feed / 60
                area = filament_area * args["E"] / length
                moves.append(dict(line=number, z=layers[-1], start=(x, y), end=(nx, ny),
                                  length=length, e=args["E"], f=feed, speed=speed,
                                  area=area, flow=area * speed, vx=speed * dx / length))
        x, y = nx, ny
    return dict(sha256=hashlib.sha256(data).hexdigest(), layers=layers, moves=moves,
                command_cap=float(settings["machine_max_speed_x"].split(",")[0]),
                rectangular_speed_at_cap=cap / (width * height),
                rounded_area=rounded_area, rounded_speed_at_cap=cap / rounded_area)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excerpt", action="store_true", help="Read the numbered test excerpt.")
    parser.add_argument("files", nargs="+", type=Path)
    options = parser.parse_args()
    started = time.perf_counter()
    reference = None
    for path in options.files:
        result = inspect(path, options.excerpt)
        moves, layers = result.pop("moves"), result.pop("layers")
        paths = Counter((seg["z"], seg["start"], seg["end"]) for seg in moves)
        length_eligible = [seg for seg in moves if seg["length"] >= 1]
        result.update(file=str(path), layer_count=len(layers), wall_moves=len(moves),
                      peak_speed=max(moves, key=lambda seg: seg["speed"]),
                      peak_flow=max(length_eligible, key=lambda seg: seg["flow"]),
                      peak_x_speed=max(moves, key=lambda seg: abs(seg["vx"])),
                      x_over_cap=sum(abs(seg["vx"]) > result["command_cap"] for seg in moves))
        if reference:
            result["matches_first_wall_paths_and_layer_grid"] = reference == (layers, paths)
        else:
            reference = layers, paths
        if options.excerpt:
            result["moves"] = moves
        print(json.dumps(result, ensure_ascii=True))
    print(json.dumps({"calculation_wall_seconds": time.perf_counter() - started}))


if __name__ == "__main__":
    main()
