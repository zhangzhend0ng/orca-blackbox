"""Feeds of the extruding moves per TOOL and feature - is a limit applied to
every extruder or only to some (two-object fixtures print one object at the
preset's wall speed and the other at the volumetric cap).

    python tools/feeds_by_tool.py <export.gcode> [feature ...]

E is the per-move extrusion length in this build. Read-only."""
import collections
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E_RE = re.compile(r"\bE(-?[0-9.]+)")
XY_RE = re.compile(r"\b[XY]-?[0-9.]+")
F_RE = re.compile(r"\bF([0-9.]+)")
T_RE = re.compile(r"^T(\d+)(?:\D|$)")
per = collections.OrderedDict()
tool = None
kind = None
feed = None
feed_ok = False
wanted = sys.argv[2:]
for raw in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = raw.split(";", 1)[0].strip()
    if raw.startswith(";TYPE:"):
        kind = raw[6:].strip()
        feed_ok = False
        continue
    if not line:
        continue
    if line[0] == "T":
        found = T_RE.match(line)
        if found:
            tool = "T" + found.group(1)
        continue
    if line[:2] not in ("G1", "G0", "G2", "G3"):
        continue
    found = F_RE.search(line)
    e, xy = E_RE.search(line), XY_RE.search(line)
    extruding = bool(e and xy and float(e.group(1)) > 0)
    if found:
        feed = found.group(1).rstrip("0").rstrip(".")
        feed_ok = not (xy and not extruding)
    if extruding and feed_ok and feed:
        per.setdefault(kind or "Custom", collections.OrderedDict()).setdefault(tool, collections.Counter())[feed] += 1
for feature, tools in per.items():
    if wanted and feature not in wanted:
        continue
    print("%-22s %s" % (feature, " | ".join("%s: %s" % (t, " ".join("%s x%d" % kv for kv in c.most_common(3))) for t, c in tools.items())))
