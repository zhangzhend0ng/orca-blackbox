"""A few facts the per-row comparison does not print, asked for by row:
bottom-surface E per mm of a run, brim moves, and whether two exports carry
the same motion once comments are stripped.

    python spot_facts.py <repo-root with the harvest> <label>=<run prefix> [...]
                        [--same-motion <run A>=<run B> ...]
"""
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HARVEST = os.environ.get("ORCA_BB_HARVEST") or os.path.join(sys.argv[1], "artifacts", "windows_mcp_harvest")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcode_facts import gcode_facts  # noqa: E402


def gcode_of(prefix):
    return glob.glob(os.path.join(glob.glob(os.path.join(HARVEST, prefix + "*"))[0], "exports", "*.gcode"))[0]


def motion(path):
    keep = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.split(";", 1)[0].rstrip()
        if line.strip():
            keep.append(line.strip())
    return keep


args = sys.argv[2:]
i = 0
while i < len(args):
    if args[i] == "--same-motion":
        for pair in args[i + 1].split(","):
            a, b = pair.split("=")
            ma, mb = motion(gcode_of(a)), motion(gcode_of(b))
            same = ma == mb
            first = next((k for k, (x, y) in enumerate(zip(ma, mb)) if x != y), None)
            print("%s vs %s: motion lines %d / %d, identical %s%s" % (a, b, len(ma), len(mb), same,
                  "" if same else " (first difference at line %s: %r | %r)" % (first, ma[first][:60], mb[first][:60])))
        i += 2
        continue
    label, prefix = args[i].split("=")
    f = gcode_facts(gcode_of(prefix))
    bottom = f["features"].get("Bottom surface", {})
    brim = f["features"].get("Brim", {})
    skirt = f["features"].get("Skirt", {})
    print("%s (%s): Bottom E/mm %s moves %s | Brim moves %s blocks %s | Skirt moves %s blocks %s | Ironing %s" % (
        label, prefix, bottom.get("e_per_mm"), bottom.get("moves"), brim.get("moves"), brim.get("blocks"),
        skirt.get("moves"), skirt.get("blocks"),
        (f["features"].get("Ironing") or {}).get("feed", {}).get("other")))
    i += 1
