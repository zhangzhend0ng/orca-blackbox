"""Which tool extrudes which feature - for the rows whose expected result is a
tool mapping (支撑主体使用工具1，接触面使用工具0 ...).

    python tool_by_feature.py <export.gcode>

E is the per-move extrusion length in this build. Read-only."""
import collections
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E_RE = re.compile(r"\bE(-?[0-9.]+)")
XY_RE = re.compile(r"\b[XY]-?[0-9.]+")
T_RE = re.compile(r"^T(\d+)(?:\D|$)")
per = collections.OrderedDict()
tool = None
kind = None
for raw in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = raw.split(";", 1)[0].strip()
    if raw.startswith(";TYPE:"):
        kind = raw[6:].strip()
        continue
    if not line:
        continue
    if line[0] == "T":
        found = T_RE.match(line)
        if found:
            tool = int(found.group(1))
        continue
    if line[:2] not in ("G1", "G0", "G2", "G3"):
        continue
    e, xy = E_RE.search(line), XY_RE.search(line)
    if e and xy and float(e.group(1)) > 0:
        per.setdefault(kind or "Custom", collections.Counter())[tool] += float(e.group(1))
for feature, tools in per.items():
    print("%-24s %s" % (feature, "  ".join("T%s %.0f" % (t, v) for t, v in sorted(tools.items(), key=lambda kv: -kv[1]))))
