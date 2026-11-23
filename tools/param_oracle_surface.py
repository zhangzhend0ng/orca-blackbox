"""What each parameter case's pilot oracle checks (read-only).

    python tools/param_oracle_surface.py          (repo root; prints TSV)

Columns: Feishu number, scenario, number of VALUES keys asserted in the
saved project, whether the G-code's layer schedule (count / last Z) is
asserted, whether ironing moves are counted, and how the oracle is built.

This is the coverage statement behind "closed": a closed case has its
parameter values verified in the reopened 3MF, every other setting
preserved, the project sliced and a G-code exported - and, for most, the
layer schedule unchanged. The Feishu rows ask for more in their expected
results 2 and 3 (feature speeds in the G-code, E per mm, tool mapping,
temperatures, geometry); those are asserted only where a column above says
so. 'closed' never means the Feishu row's three expected results all hold.
"""

import importlib
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from harness import native_pilots  # noqa: E402

import io
out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
seen = set()
for scenario, module in sorted(native_pilots.TRIALS.items()):
    if not scenario.startswith("uia_param_"):
        continue
    try:
        m = importlib.import_module("harness." + module)
    except Exception as exc:  # noqa: BLE001
        print(scenario, "IMPORT FAIL", exc)
        continue
    cid = getattr(m, "CASE_ID", "")
    found = re.search(r"_(\d{3})(_|$)", cid)
    if not found:
        continue
    num = found.group(1)
    src = Path(m.__file__).read_text(encoding="utf-8")
    values = getattr(m, "VALUES", None)
    keys = len(values) if values else len(getattr(m, "LAYER_PAIR", {}) or {})
    schedule = bool(re.search(r"schedule=\{", src)) or "analyze_gcode(" in src
    ironing = "ironing=" in src
    own = "def verify_business" in src
    dev = "develop" in src
    out.write("\t".join([num, scenario.replace("uia_param_", ""), str(keys),
                         "schedule" if schedule else "-", "ironing" if ironing else "-",
                         "own-verify" if own else "make_verify", module]) + "\n")
    seen.add(num)
out.flush()
print("cases with a pilot:", len(seen), file=sys.stderr)
