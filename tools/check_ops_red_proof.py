"""Red proofs for tools/check_ops_against_atlas.py (in-process, no file is
touched). Each rule of the checker must turn red on a bad input:
  1. baseline: 0 problems, exit 0;
  2. a label that is on no row line is a problem;
  3. a conditional row whose proof entry is removed is a problem again;
  4. a target that is in no popup census is a problem - unless exactly that
     target is PENDING (a note), and a different target under the same
     pending entry is a problem again;
  5. a wrong target is a problem against the census too.

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
GOOD_POPUPS = list(chk.POPUPS)
# the state before the 'Wall type' popup was censused (fa706g3 run 2bacb634)
NO_WALL_TYPE = [p for p in GOOD_POPUPS if not (p["tab"] == "Multimaterial" and p["row"] == "Wall type")]
PEND_CONE = {("uia_param_prime_tower", 2): ("Cone", "synthetic pending entry for the proof")}
OPS_KEY = "uia_param_prime_tower op[2] combo TARGET"


def run(ops, cond, pend, popups):
    chk.PARAM_OPS, chk.CONDITIONAL, chk.PENDING_TARGET, chk.POPUPS = ops, cond, pend, popups
    out = io.StringIO()
    with redirect_stdout(out):
        rc = chk.main()
    return rc, out.getvalue()


results = []
rc, out = run(GOOD_OPS, GOOD_COND, GOOD_PEND, GOOD_POPUPS)
results.append(("baseline: 0 problems, exit 0", rc == 0 and "all ops validate" in out))

bad = copy.deepcopy(GOOD_OPS)
bad["uia_param_first_speeds"][0]["label"] = ["^First layer spead"]
rc, out = run(bad, GOOD_COND, GOOD_PEND, GOOD_POPUPS)
results.append(("a label that is on no row line is a problem (exit 1)",
                rc == 1 and "uia_param_first_speeds op[0] label" in out and "problems" in out))

cond = {k: v for k, v in GOOD_COND.items() if k != ("uia_param_raft", "Raft contact Z distance")}
rc, out = run(GOOD_OPS, cond, GOOD_PEND, GOOD_POPUPS)
results.append(("a conditional row without its proof entry is a problem again",
                rc == 1 and "uia_param_raft op[" in out and "Raft contact" in out
                and "no candidate" in out))

rc, out = run(GOOD_OPS, GOOD_COND, {}, NO_WALL_TYPE)
results.append(("an uncensused target without a pending entry is a problem",
                rc == 1 and OPS_KEY + " 'Cone'" in out))

rc, out = run(GOOD_OPS, GOOD_COND, PEND_CONE, NO_WALL_TYPE)
results.append(("... the same target under its pending entry is a note (exit 0)",
                rc == 0 and "PENDING run proof" in out))

bad2 = copy.deepcopy(GOOD_OPS)
bad2["uia_param_prime_tower"][2]["target"] = "Polygon"
rc, out = run(bad2, GOOD_COND, PEND_CONE, NO_WALL_TYPE)
results.append(("... and a different target under that entry is a problem",
                rc == 1 and OPS_KEY + " 'Polygon'" in out))

rc, out = run(bad2, GOOD_COND, GOOD_PEND, GOOD_POPUPS)
results.append(("a wrong target is a problem against the popup census",
                rc == 1 and "uia_param_prime_tower op[2] TARGET 'Polygon'" in out))

for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
sys.exit(0 if all(ok for _n, ok in results) else 1)
