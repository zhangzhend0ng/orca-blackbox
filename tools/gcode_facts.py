"""What an exported G-code shows, feature by feature - the numbers the Feishu
rows name in their expected results 2 and 3 (feeds, layer heights, tools,
temperatures, arcs, widths), read from files the runs already harvest.

    python tools/gcode_facts.py <file.gcode> [--json]

Nothing here judges. Every fact is reported with the number of moves it
rests on, and a feature the model never needed (bridges on a cube, support
without support enabled) is absent - absence is reported as absent.

Reading rules: Orca groups moves under `;TYPE:<name>` and starts each
layer with `;LAYER_CHANGE`. F is modal; an extruding move counts for the
current F unless that F was set by a travel move (the entry travel's feed
is not the feature's) - a feed set by an F-only, retract or prime line
carries into the block, which matters on the first layer, where the walls
run at the prime's F without any F line inside the block (run 1f8c9236).
E on a move is the filament length of THAT move (each side of the cube
carries the same E3.00173; M82 is not in the file) unless the file says
M82, in which case it is a position and the difference to the previous E
is used. "First" is layer 1, "other" every later layer. A move that lowers
XY travel between `;WIPE_START` and `;WIPE_END` is a wipe (seam wiping).
Widths come from the `;WIDTH:` lines Orca writes before a wall whose width
differs from the nominal one (Arachne).
"""
import collections
import json
import math
import re
import sys

F_RE = re.compile(r"\bF([0-9.]+)")
COORD_RE = re.compile(r"\b([XYEZ])(-?[0-9.]+)")
ACCEL_RE = re.compile(r"\bACCEL=([0-9.]+)")
T_RE = re.compile(r"^T(\d+)(?:\D|$)")
FIRST = "first"
OTHER = "other"


def _bucket(layer):
    return FIRST if layer <= 1 else OTHER


def _num(text):
    return text.rstrip("0").rstrip(".") if "." in text else text


def _new_feature():
    return {"blocks": 0, "moves": 0, "feed": {FIRST: {}, OTHER: {}},
            "e": 0.0, "length": 0.0, "retracts": 0, "primes": 0}


def gcode_facts(path):
    out = {"layers": 0, "z": [], "height": [], "features": {}, "travel": {FIRST: {}, OTHER: {}},
           "wipe": {"moves": 0, "feed": {}, "e": 0.0},
           "arcs": {"extruding": 0, "travel": 0}, "tools": [], "e_by_tool": {},
           "temps": [], "fan": {}, "fan_aux": {}, "accel": {}, "widths": {},
           "object_labels": 0, "numbered_lines": 0, "verbose_comment_lines": 0,
           "feature_order": []}
    layer = 0
    kind = None
    feed = None
    feed_ok = False
    absolute_e = False
    e_last = None
    x = y = None
    tool = None
    wiping = False
    with open(path, encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            line = raw.split(";", 1)[0].strip()
            if raw.startswith(";LAYER_CHANGE"):
                layer += 1
                out["layers"] += 1
                continue
            if raw.startswith(";TYPE:"):
                kind = raw[6:].strip()
                if kind not in out["features"]:
                    out["features"][kind] = _new_feature()
                    out["feature_order"].append(kind)
                out["features"][kind]["blocks"] += 1
                continue
            if raw.startswith(";Z:"):
                out["z"].append(raw[3:].strip())
                continue
            if raw.startswith(";HEIGHT:"):
                out["height"].append(raw[8:].strip())
                continue
            if raw.startswith(";WIDTH:"):
                key = "%.3f" % float(raw[7:])
                out["widths"][key] = out["widths"].get(key, 0) + 1
                continue
            if raw.startswith(";WIPE_START"):
                wiping = True
                continue
            if raw.startswith(";WIPE_END"):
                wiping = False
                continue
            if "EXCLUDE_OBJECT" in raw:
                out["object_labels"] += 1
            if line[:1] == "N" and line[1:2].isdigit():
                out["numbered_lines"] += 1
            if line[:1] in "GM" and " ; " in raw:
                out["verbose_comment_lines"] += 1
            if not line:
                continue
            if line[:3] == "M82":
                absolute_e, e_last = True, None
                continue
            if line[:3] == "M83":
                absolute_e = False
                continue
            if line[0] == "T":
                found = T_RE.match(line)
                if found:
                    tool = int(found.group(1))
                    out["tools"].append(tool)
                continue
            if line.startswith("M104") or line.startswith("M109"):
                if line not in out["temps"]:
                    out["temps"].append(line)
                continue
            if line.startswith("M106"):
                s = re.search(r"\bS(\d+)", line)
                val = "S" + (s.group(1) if s else "?")
                aux = "P2" in line
                table = out["fan_aux"] if aux else out["fan"]
                table[val] = table.get(val, 0) + 1
                continue
            if line.startswith("SET_VELOCITY_LIMIT"):
                found = ACCEL_RE.search(line)
                if found:
                    key = _num(found.group(1))
                    out["accel"][key] = out["accel"].get(key, 0) + 1
                continue
            if line[:2] not in ("G0", "G1", "G2", "G3"):
                continue
            if line[:3] == "G92":
                e_last = None
                continue
            coords = {m.group(1): float(m.group(2)) for m in COORD_RE.finditer(line)}
            found = F_RE.search(line)
            if found:
                feed = _num(found.group(1))
            moving_xy = "X" in coords or "Y" in coords
            length = 0.0
            if moving_xy and x is not None and y is not None:
                length = math.hypot(coords.get("X", x) - x, coords.get("Y", y) - y)
            e = coords.get("E")
            delta = None
            if e is not None:
                delta = (e - e_last) if (absolute_e and e_last is not None) else e
            lifts = "Z" in coords
            extruding = delta is not None and delta > 0 and moving_xy and not lifts
            arc = line[:2] in ("G2", "G3")
            if found:
                # A feed set by a travel move is the entry travel's; one set by
                # an F-only, retract or prime line carries over into the block
                # (the first layer's walls run at the prime's F1800 in run
                # 1f8c9236 without any F line inside the block).
                feed_ok = not (moving_xy and not extruding)
            if extruding:
                feature = out["features"].setdefault(kind or "Custom", _new_feature())
                bucket = _bucket(layer)
                feature["moves"] += 1
                feature["e"] += delta
                feature["length"] += length
                if feed_ok and feed:
                    feature["feed"][bucket][feed] = feature["feed"][bucket].get(feed, 0) + 1
                if tool is not None:
                    out["e_by_tool"][str(tool)] = round(out["e_by_tool"].get(str(tool), 0.0) + delta, 3)
                if arc:
                    out["arcs"]["extruding"] += 1
            elif moving_xy:
                if wiping and delta is not None and delta < 0:
                    out["wipe"]["moves"] += 1
                    out["wipe"]["e"] += delta
                    if feed:
                        out["wipe"]["feed"][feed] = out["wipe"]["feed"].get(feed, 0) + 1
                elif feed:
                    b = out["travel"][_bucket(layer)]
                    b[feed] = b.get(feed, 0) + 1
                if arc:
                    out["arcs"]["travel"] += 1
            elif delta is not None:
                feature = out["features"].setdefault(kind or "Custom", _new_feature())
                feature["primes" if delta > 0 else "retracts"] += 1
            if "X" in coords:
                x = coords["X"]
            if "Y" in coords:
                y = coords["Y"]
            if e is not None:
                e_last = e
    for feature in out["features"].values():
        feature["e_per_mm"] = round(feature["e"] / feature["length"], 5) if feature["length"] else None
        for bucket in (FIRST, OTHER):
            feature["feed"][bucket] = _ranked(feature["feed"][bucket])
        feature["e"] = round(feature["e"], 3)
        feature["length"] = round(feature["length"], 1)
    for bucket in (FIRST, OTHER):
        out["travel"][bucket] = _ranked(out["travel"][bucket])
    out["wipe"]["feed"] = _ranked(out["wipe"]["feed"])
    out["wipe"]["e"] = round(out["wipe"]["e"], 3)
    out["tool_changes"] = len(out["tools"])
    out["z_steps"] = _counts(out["height"])
    out["z_first"] = out["z"][0] if out["z"] else None
    out["z_last"] = out["z"][-1] if out["z"] else None
    del out["z"], out["height"]
    return out


def _ranked(table, limit=4):
    return " ".join("F%s x%d" % (f, n) for f, n in sorted(table.items(), key=lambda kv: -kv[1])[:limit]) or "-"


def _counts(values):
    counts = collections.OrderedDict()
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(counts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    facts = gcode_facts(args[0])
    if "--json" in sys.argv:
        print(json.dumps(facts, sort_keys=True))
        return 0
    print("layers %d | first Z %s | last Z %s | steps %s" % (
        facts["layers"], facts["z_first"], facts["z_last"], facts["z_steps"]))
    print("tools %s | E by tool %s" % (facts["tools"], facts["e_by_tool"]))
    print("temps %s" % facts["temps"][:8])
    print("fan %s | aux %s | accel %s" % (facts["fan"], facts["fan_aux"], facts["accel"]))
    print("arcs %s | widths %s | EXCLUDE_OBJECT %d | numbered %d | verbose %d" % (
        facts["arcs"], facts["widths"], facts["object_labels"], facts["numbered_lines"],
        facts["verbose_comment_lines"]))
    print("travel first: %-40s | other: %s" % (facts["travel"][FIRST], facts["travel"][OTHER]))
    print("wipe %s" % facts["wipe"])
    for kind in facts["feature_order"]:
        row = facts["features"][kind]
        print("%-24s blocks %3d moves %5d | first: %-34s | other: %-34s | E/mm %s | retract %d" % (
            kind, row["blocks"], row["moves"], row["feed"][FIRST], row["feed"][OTHER],
            row["e_per_mm"], row["retracts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
