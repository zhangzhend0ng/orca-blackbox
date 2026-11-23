"""Feed rates per feature type in an exported G-code - the part of a case's
expected result that lives in the G-code itself ("首层外墙/内墙 F≈1800，
填充 F≈2400，空驶 F≈9000" and the like), read from the file we already
harvest.

    python tools/gcode_feature_speeds.py <file.gcode> [--json] [--travel]

Orca groups moves under `;TYPE:<name>` comments and starts each layer with
`;LAYER_CHANGE`. A feature's feed is the F on its extruding moves (mm/min =
mm/s x 60). F is modal in G-code, and the first extruding move of a block
often carries the feed of whatever ran before it (the entry travel), so a
move is counted only once an F was set INSIDE the current block. Printed per
type: the distinct feeds on the first layer and on the others with the
number of moves. --travel adds the feeds of the non-extruding XY moves per
layer band (travel speed lives there).

Only what the file contains: a feature the model never needed (bridges on a
cube, support ironing without support) is absent, and absence is reported as
absent - it is not a pass.

Measured on the cube fixture (2026-11-24, the regression G-codes): walls
and sparse infill run at F ~1865-1870 on the other layers although the
preset says 100 / 150 / 200 mm/s - the fixture's filament allows
filament_max_volumetric_speed 10 mm3/s and its lines are 0.82 x 0.4 mm, so
10 / 0.328 = 30.5 mm/s is the ceiling. The Feishu rows take their feed
numbers from the 0.4 mm nozzle at 0.20 mm layers (their precondition), where
the same limit allows ~120 mm/s. First-layer feeds below the ceiling are
observable (#270: walls F1800, infill F2400), feeds above it are not.
"""
import json
import re
import sys

F_RE = re.compile(r"\bF([0-9.]+)")
E_RE = re.compile(r"\bE(-?[0-9.]+)")
XY_RE = re.compile(r"\b[XY](-?[0-9.]+)")


def feature_speeds(path, travel=False):
    """{type: {"first": {feed: moves}, "other": {feed: moves}, "blocks": n}};
    with travel: the same shape under the key "travel" (non-extruding XY
    moves, outside TYPE blocks or inside)."""
    out = {}
    layer = 0
    kind = None
    feed = None
    feed_in_block = False
    e_last = None
    x_last = y_last = None

    def bucket(name):
        row = out.setdefault(name, {"first": {}, "other": {}, "blocks": 0})
        return row["first"] if layer <= 1 else row["other"]

    with open(path, encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            line = raw.split(";", 1)[0].strip()
            comment = raw[1:].strip() if raw.startswith(";") else ""
            if comment.startswith("TYPE:"):
                kind = comment[5:].strip()
                feed_in_block = False
                out.setdefault(kind, {"first": {}, "other": {}, "blocks": 0})["blocks"] += 1
                continue
            if comment.startswith("LAYER_CHANGE"):
                layer += 1
                continue
            if not line or line[0] != "G":
                continue
            opcode = line.split()[0]
            if opcode == "G92":
                e = E_RE.search(line)
                if e:
                    e_last = float(e.group(1))
                continue
            if opcode not in ("G0", "G1", "G2", "G3"):
                continue
            found = F_RE.search(line)
            if found:
                feed = float(found.group(1))
                if kind is not None:
                    feed_in_block = True
            coords = {m.group(1): float(m.group(2))
                      for m in re.finditer(r"\b([XYE])(-?[0-9.]+)", line)}
            e = coords.get("E")
            moving_xy = ("X" in coords or "Y" in coords)
            if e is not None and e_last is not None and e > e_last and moving_xy and kind is not None:
                if feed_in_block and feed:
                    b = bucket(kind)
                    b[feed] = b.get(feed, 0) + 1
            elif travel and moving_xy and (e is None or (e_last is not None and e <= e_last)):
                if feed:
                    b = bucket("travel")
                    b[feed] = b.get(feed, 0) + 1
            if e is not None:
                e_last = e
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0]
    data = feature_speeds(path, travel="--travel" in sys.argv)
    if "--json" in sys.argv:
        print(json.dumps(data, sort_keys=True))
        return 0
    for kind, row in sorted(data.items()):
        fmt = lambda d: " ".join("%g x%d" % (f, n) for f, n in sorted(d.items(), key=lambda kv: -kv[1])[:6]) or "-"
        print("%-24s blocks %3d | first layer: %-44s | other layers: %s" % (
            kind, row["blocks"], fmt(row["first"]), fmt(row["other"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
