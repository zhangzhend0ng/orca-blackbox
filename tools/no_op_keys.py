"""Keys of each parameter case that sit at the case's target in the CUBE fixture
(so the ops may never touch them) but not in ANOTHER fixture: those cases will
end with pilot_target_setting_mismatch there unless an op drives the key.

    python tools/no_op_keys.py <repo-root> <other fixture.3mf>

Read-only."""
import io
import json
import sys
import zipfile
from decimal import Decimal, InvalidOperation

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root, other = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
from harness import native_pilots  # noqa: E402
from harness.native_script_baseline import PARAM_OPS  # noqa: E402


def config(path):
    return json.loads(zipfile.ZipFile(path).read("Metadata/project_settings.config").decode("utf-8-sig"))


def same(a, b):
    if isinstance(a, list) and len(a) == 1:
        a = a[0]
    if isinstance(b, list) and len(b) == 1:
        b = b[0]
    if a == b:
        return True
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, TypeError, ValueError):
        return False


cube = config(root + "/fixtures/agent_layer_cube.3mf")
new = config(other)
total = 0
for scenario, module in sorted(native_pilots.TRIALS.items()):
    if not scenario.startswith("uia_param_") or scenario not in PARAM_OPS:
        continue
    pilot = native_pilots.pilot_module(scenario)
    values = getattr(pilot, "VALUES", None)
    if not values:
        continue
    hit = [k for k, want in values.items() if same(cube.get(k), want) and not same(new.get(k), want)]
    driven = [k for k in hit if any(str(want_of) in json.dumps(op, ensure_ascii=False)
                                    for op in PARAM_OPS[scenario] for want_of in [values[k]]
                                    if op.get("op") == "float" and op.get("value") == values[k])]
    total += len(hit)
    if hit:
        print("%-30s %s" % (scenario, ", ".join("%s(%s->%s)" % (k, new.get(k), values[k]) for k in hit)))
print("keys at target on the cube but not on the other fixture:", total)
