"""Offline modal fan and feed audit for the FDMT exports used by Feishu #265."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import re
from time import perf_counter


SURFACES = {"Bottom surface", "Top surface"}
OVERHANG = {"Overhang wall", "Bridge"}
WALLS = {"Outer wall", "Overhang wall"}
SETTINGS = {
    "slowdown_for_curled_perimeters", "enable_overhang_bridge_fan", "overhang_fan_speed",
    "overhang_fan_threshold", "internal_bridge_fan_speed", "fan_min_speed", "fan_max_speed",
    "reduce_fan_stop_start_freq", "close_fan_the_first_x_layers", "full_fan_speed_layer",
    "slow_down_for_layer_cooling", "slow_down_layer_time", "slow_down_min_speed",
    "dont_slow_down_outer_wall", "additional_cooling_fan_speed", "gcode_flavor",
}
PARAMETER = re.compile(r"([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))")


@dataclass
class Deposit:
    line: int
    feed: float
    feed_line: int
    fan: float
    fan_line: int


def scan(path):
    data = path.read_bytes()
    rows = data.decode("utf-8").splitlines()
    layers, fan_commands = [], Counter()
    deposits = defaultdict(list)
    modal = defaultdict(Counter)
    overhang_layer_fan = Counter()
    pwm_204 = []
    config = {}
    role, tool, fan, feed = None, None, None, None
    xy = (None, None)
    wiping, absolute_xy, relative_e = False, True, False
    for number, raw in enumerate(rows, 1):
        if raw.startswith("; "):
            key, _, value = raw[2:].partition(" = ")
            if key in SETTINGS:
                config[key] = value
        if raw.startswith(";Z:"):
            layers.append(raw[3:].strip())
        elif raw.startswith(";TYPE:"):
            role = raw[6:].strip()
        elif raw in {";WIPE_START", ";WIPE_END"}:
            wiping = raw == ";WIPE_START"
        op, _, arguments = raw.partition(";")[0].strip().partition(" ")
        if op in {"G90", "G91"}:
            absolute_xy = op == "G90"
        elif op in {"M82", "M83"}:
            relative_e = op == "M83"
        elif re.fullmatch(r"T\d+", op):
            tool = op
        elif op in {"M106", "M107"}:
            params = {letter: float(value) for letter, value in PARAMETER.findall(arguments)}
            channel = int(params.get("P", 0))
            pwm = params.get("S", 255) if op == "M106" else 0
            fan_commands[f"P{channel} S{pwm:g}"] += 1
            if pwm == 204:
                pwm_204.append([number, channel, raw])
            if channel == 0:
                fan, fan_line = pwm, number
        elif op in {"G0", "G1", "G2", "G3"}:
            params = {letter: float(value) for letter, value in PARAMETER.findall(arguments)}
            if not absolute_xy:
                raise ValueError(f"Unexpected relative XY at {path}:{number}")
            if "F" in params:
                feed, feed_line = params["F"], number
            next_xy = (params.get("X", xy[0]), params.get("Y", xy[1]))
            if layers and role and not wiping and params.get("E", 0) > 0 and xy != next_xy:
                if not relative_e or None in (*xy, *next_xy, feed, fan) or tool != "T0":
                    raise ValueError(f"Unexpected deposition format at {path}:{number}")
                arc = (op, params.get("I"), params.get("J"), params.get("R")) if op in {"G2", "G3"} else ()
                key = (len(layers), role, *xy, *next_xy, *arc)
                modal[role][f"S{fan:g}"] += 1
                if role in OVERHANG | {"Internal Bridge", "Internal bridge"}:
                    overhang_layer_fan[(len(layers), fan)] += 1
                if role in SURFACES | OVERHANG | WALLS:
                    deposits[key].append(Deposit(number, feed, feed_line, fan, fan_line))
            xy = next_xy
    summary = {
        "sha256": hashlib.sha256(data).hexdigest(), "layers": len(layers),
        "settings": config, "fan_commands": fan_commands, "exact_pwm_204_commands": pwm_204,
        "deposits_by_role_and_modal_part_fan": dict(modal),
        "overhang_deposits_on_first_layer": {f"S{fan:g}": count for (layer, fan), count
                                             in overhang_layer_fan.items() if layer == 1},
        "duplicated_keys": sum(len(group) > 1 for group in deposits.values()),
    }
    return summary, layers, rows, deposits


def compare(base, modified):
    old_summary, old_layers, old_rows, old_moves = base
    summary, layers, rows, moves = modified
    if old_layers != layers:
        raise ValueError("Layer metadata differs between the exports")
    matched, old_only, new_only, fan_hits = (Counter() for _ in range(4))
    surface_feed, surface_layers = Counter(), defaultdict(Counter)
    surface_fan, wall_slowdown = Counter(), Counter()
    examples = {}
    for key in old_moves.keys() | moves.keys():
        layer, role, *_ = key
        old, new = old_moves.get(key, ()), moves.get(key, ())
        matched[role] += min(len(old), len(new))
        old_only[role] += max(0, len(old) - len(new))
        new_only[role] += max(0, len(new) - len(old))
        for before, after in zip(old, new):
            delta = after.feed - before.feed
            if role in WALLS and delta < -0.6:
                wall_slowdown[role] += 1
            if role in OVERHANG and abs(after.fan - 204) <= 1 and after.fan != before.fan:
                fan_hits[role] += 1
            if role in SURFACES and before.fan != after.fan:
                surface_fan[role] += 1
            if role in SURFACES and abs(delta) >= 0.6:
                transition = f"{role}: F{before.feed:g}->F{after.feed:g}"
                surface_feed[transition] += 1
                surface_layers[f"{layer} (Z{layers[layer - 1]})"][transition] += 1
                if transition not in examples or after.line < examples[transition]["modified"]["deposit_line"]:
                    examples[transition] = {
                        "layer": layer, "xy": key[2:6],
                        "baseline": example(before, old_rows), "modified": example(after, rows),
                    }
    return {
        "baseline_sha256": old_summary["sha256"], "modified_sha256": summary["sha256"],
        "matched": matched, "baseline_only": old_only, "modified_only": new_only,
        "overhang_80pct_matches": fan_hits, "wall_slowdowns": wall_slowdown,
        "surface_fan_changes": surface_fan, "surface_feed_transitions": surface_feed,
        "surface_feed_changes_by_layer": dict(sorted(surface_layers.items(), key=lambda p: int(p[0].split()[0]))),
        "first_surface_example_for_each_feed_transition": examples,
    }


def example(deposit, rows):
    return {
        "deposit_line": deposit.line, "deposit": rows[deposit.line - 1],
        "feed_line": deposit.feed_line, "feed_command": rows[deposit.feed_line - 1],
        "fan_line": deposit.fan_line, "fan_command": rows[deposit.fan_line - 1],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("modified", type=Path, nargs="+")
    args = parser.parse_args()
    start = perf_counter()
    base = scan(args.baseline)
    variants = [scan(variant) for variant in args.modified]
    output = {"hostname": platform.node(), "baseline": base[0],
              "variants": [item[0] for item in variants],
              "pairs": [compare(base, item) for item in variants],
              "elapsed_seconds": round(perf_counter() - start, 3)}
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
