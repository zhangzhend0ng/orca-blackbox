"""Red proofs for tools/check_ops_against_atlas.py (in-process, no file is
touched): (1) a broken label must be a problem; (2) a conditional row whose
proof entry is removed must be a problem again; (3) an unknown target
without a pending entry must be a problem.

Usage (from the tree root): python <this>.py
"""
import copy
import io
import sys
from contextlib import redirect_stdout

sys.path.insert(0, ".")
import tools.check_ops_against_atlas as chk  # noqa: E402

GOOD_OPS = copy.deepcopy(chk.PARAM_OPS)
GOOD_COND = dict(chk.CONDITIONAL)
GOOD_PEND = dict(chk.PENDING_TARGET)


def run(ops, cond, pend):
    chk.PARAM_OPS, chk.CONDITIONAL, chk.PENDING_TARGET = ops, cond, pend
    out = io.StringIO()
    with redirect_stdout(out):
        rc = chk.main()
    return rc, out.getvalue()


results = []
rc, out = run(GOOD_OPS, GOOD_COND, GOOD_PEND)
results.append(("baseline: 0 problems, exit 0", rc == 0 and "all ops validate" in out))

bad = copy.deepcopy(GOOD_OPS)
bad["uia_param_first_speeds"][0]["label"] = ["^First layer spead"]
rc, out = run(bad, GOOD_COND, GOOD_PEND)
results.append(("a label that is on no row line is a problem (exit 1)",
                rc == 1 and "uia_param_first_speeds op[0] label" in out and "problems" in out))

cond = {k: v for k, v in GOOD_COND.items() if k != ("uia_param_raft", 1)}
rc, out = run(GOOD_OPS, cond, GOOD_PEND)
results.append(("a conditional row without its proof entry is a problem again",
                rc == 1 and "uia_param_raft op[1] label" in out))

pend = {}
rc, out = run(GOOD_OPS, GOOD_COND, pend)
results.append(("an uncensused target without a pending entry is a problem",
                rc == 1 and "uia_param_prime_tower op[2] combo TARGET 'Cone'" in out))

bad2 = copy.deepcopy(GOOD_OPS)
bad2["uia_param_prime_tower"][2]["target"] = "Polygon"
rc, out = run(bad2, GOOD_COND, GOOD_PEND)
results.append(("a wrong target inside a pending entry is still a problem",
                rc == 1 and "uia_param_prime_tower op[2] combo TARGET 'Polygon'" in out))
for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
sys.exit(0 if all(ok for _n, ok in results) else 1)
