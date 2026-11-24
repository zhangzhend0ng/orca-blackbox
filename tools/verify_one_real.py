"""Re-run the session's verifier on one harvested run with the masking removed:
when the verifier catches a non-evidence exception it prints
"native_evidence_unavailable"; here the real exception and its traceback are
shown instead.

    python tools/verify_one_real.py <run-id prefix>   (from the worktree whose HEAD produced the run)

The module is rebuilt in memory from its own source (the except clause is
rewritten), so no file is touched. Run it from the worktree whose HEAD produced the run. Read-only on the harvest.
"""
import glob
import io
import json
import os
import sys
import traceback
import types

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
import harness.native_save_session as original  # noqa: E402
from harness.runtime_ports import ExecutionOutcome, VerificationSnapshot  # noqa: E402

MASK = 'detail = str(exc) if isinstance(exc, _InvalidEvidence) else "native_evidence_unavailable"'
src = open(original.__file__, encoding="utf-8").read()
assert src.count(MASK) >= 1, src.count(MASK)
# keep the context of the failure: re-raise instead of masking
src = src.replace("    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,\n"
                  "            struct.error, DecimalException, ET.ParseError, zipfile.BadZipFile,",
                  "    except BaseException as _real:  # DIAGNOSTIC\n"
                  "        import traceback as _tb\n"
                  "        _tb.print_exception(type(_real), _real, _real.__traceback__, limit=10)\n"
                  "        raise\n"
                  "    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,\n"
                  "            struct.error, DecimalException, ET.ParseError, zipfile.BadZipFile,")
assert "DIAGNOSTIC" in src
module = types.ModuleType("harness.native_save_session_diag")
module.__file__ = original.__file__
module.__package__ = "harness"
exec(compile(src, original.__file__, "exec"), module.__dict__)

prefix = sys.argv[1]
directory = [h for h in glob.glob(os.path.join("artifacts", "windows_mcp_harvest", prefix + "*")) if os.path.isdir(h)][0]
run_id = os.path.basename(directory)
art = os.path.join(directory, "artifacts") if os.path.isdir(os.path.join(directory, "artifacts")) else directory
from pathlib import Path  # noqa: E402
art = Path(art)
manifest = json.load(open(os.path.join(directory, "manifest.json"), encoding="utf-8-sig"))
scope = json.load(open(os.path.join(directory, "scope.json"), encoding="utf-8-sig"))
scenario = scope["scenario"]
snapshot = VerificationSnapshot(module.native_contract("script", scenario), run_id, art, manifest,
                                ExecutionOutcome("completed"))
try:
    outcome = module.verify_saved(snapshot, cancelled=lambda: False)
    print(scenario, "evidence_complete", outcome.evidence_complete, "compliant", outcome.execution_compliant)
    for name, check in outcome.checks.items():
        print("  ", name, check.status, str(check.detail)[:300])
except BaseException as exc:  # noqa: BLE001
    print("RAISED", type(exc).__name__, exc)
