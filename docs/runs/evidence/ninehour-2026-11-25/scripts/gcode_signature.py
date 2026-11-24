"""Aggregate signature of an exported G-code, to compare two slices of one model.

    python -B docs/runs/evidence/ninehour-2026-11-25/scripts/gcode_signature.py A.gcode B.gcode

Why an aggregate: tonight the cube exports came out line for line the same run after run, but the
FDM test model did not - two runs of one build on one machine emitted the same paths in another
order and cut into another number of moves. A line diff therefore says nothing for that model. What
does not depend on the order or the cut is, per (TYPE section, layer, feed): the length extruded,
and per (TYPE section, layer): the filament used. signature() adds those up; compare() counts the
entries that differ by more than TOLERANCE.

Read-only; the file is read up to its config block ("; CONFIG_BLOCK_START"). Extrusion is read as
the file declares it (M83 relative, M82 absolute); a move counts as extruding when it uses filament
and travels in X or Y. Arcs (G2/G3) count by their chord.
"""
from __future__ import annotations

import collections
import json
import math
import sys

TOLERANCE = 0.05          # mm: far above float noise, far below the smallest real difference


def signature(path):
    relative, layer, feed, type_name = False, 0, None, "(none)"
    x = y = e = None
    length, filament, moves = collections.defaultdict(float), collections.defaultdict(float), collections.Counter()
    with open(path, encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if line.startswith("; CONFIG_BLOCK_START"):
                break
            if line.startswith(";LAYER_CHANGE"):
                layer += 1
                continue
            if line.startswith(";TYPE:"):
                type_name = line[6:]
                continue
            if line in ("M83", "M82"):
                relative = line == "M83"
                continue
            if line[:3] not in ("G0 ", "G1 ", "G2 ", "G3 "):
                continue
            new_x, new_y, new_e = x, y, None
            for word in line[3:].split():
                if word[0] == "X":
                    new_x = float(word[1:])
                elif word[0] == "Y":
                    new_y = float(word[1:])
                elif word[0] == "E":
                    new_e = float(word[1:])
                elif word[0] == "F":
                    feed = float(word[1:])
            distance = None if None in (x, y, new_x, new_y) else math.hypot(new_x - x, new_y - y)
            used = None if new_e is None else (new_e if relative or e is None else new_e - e)
            if new_e is not None:
                e = new_e if not relative else (e or 0) + new_e
            x, y = new_x, new_y
            if not used or used <= 0 or not distance or distance <= 0:
                continue
            key = "%s|%d" % (type_name, layer)
            length["%s|%s" % (key, "-" if feed is None else "%.1f" % feed)] += distance
            filament[key] += used
            moves[type_name] += 1
    return {"layers": layer, "extruding_moves": sum(moves.values()), "moves_by_type": dict(sorted(moves.items())),
            "length_by_type_layer_feed": {k: round(v, 4) for k, v in sorted(length.items())},
            "filament_by_type_layer": {k: round(v, 4) for k, v in sorted(filament.items())}}


def _differing(first, second):
    keys = sorted(set(first) | set(second))
    differing = [k for k in keys if abs(first.get(k, 0.0) - second.get(k, 0.0)) > TOLERANCE]
    return {"entries": [len(first), len(second)], "differing": len(differing),
            "total": [round(sum(first.values()), 3), round(sum(second.values()), 3)],
            "examples": [[k, first.get(k), second.get(k)] for k in differing[:8]]}


def compare_signatures(a, b):
    """What differs between two signatures; `same` is True when nothing does."""
    out = {"layers": [a["layers"], b["layers"]], "extruding_moves": [a["extruding_moves"], b["extruding_moves"]],
           "length_by_type_layer_feed": _differing(a["length_by_type_layer_feed"], b["length_by_type_layer_feed"]),
           "filament_by_type_layer": _differing(a["filament_by_type_layer"], b["filament_by_type_layer"])}
    out["moves_by_type"] = {k: [a["moves_by_type"].get(k, 0), b["moves_by_type"].get(k, 0)]
                            for k in sorted(set(a["moves_by_type"]) | set(b["moves_by_type"]))}
    out["types_whose_move_count_changed"] = sorted(k for k, (x, y) in out["moves_by_type"].items() if x != y)
    out["same"] = (out["layers"][0] == out["layers"][1] and not out["length_by_type_layer_feed"]["differing"]
                   and not out["filament_by_type_layer"]["differing"])
    return out


def compare(first, second):
    return compare_signatures(signature(first), signature(second))


if __name__ == "__main__":
    print(json.dumps(compare(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
