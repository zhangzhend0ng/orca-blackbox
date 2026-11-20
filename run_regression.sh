#!/bin/bash
# Single source of truth for the case list: cases.py (see docs/STRUCTURING_PLAN.md).
# Do NOT hardcode case names here. Suite filter and only-failed live below.
PY=./.venv/Scripts/python.exe
[ -x "$PY" ] || PY=python
CASES=$($PY -c "from cases import enabled_cases; print(' '.join(enabled_cases('regression')))")
if [ -z "$CASES" ]; then echo "ERROR: empty regression list from cases.py"; exit 2; fi
# --only-failed: rerun just artifacts/failed_cases.txt if present and non-empty
if [ "$1" == "--only-failed" ] && [ -s artifacts/failed_cases.txt ]; then
  CASES=$(cat artifacts/failed_cases.txt)
  echo "=== only-failed: $CASES ==="
fi
PASS=0; FAIL=0; FAILED=""
BATCH=""
rm -f artifacts/junit.xml artifacts/failed_cases.txt
for c in $CASES; do
  echo "=== $c ==="
  case_file=$("$PY" -c 'import sys; from cases import case_path; p = case_path(sys.argv[1]); sys.exit(2) if p is None else print(p)' "$c")
  if [ $? -ne 0 ] || [ -z "$case_file" ]; then
    echo "ERROR: no registry path for $c"; exit 2
  fi
  run_id=$("$PY" -c 'from uuid import uuid4; print(uuid4().hex)') || exit 2
  ORCA_BB_PERF_RUN_ID=$run_id ORCA_BB_PERF_LABEL=$c "$PY" "$case_file" > "artifacts/regress_${c}.log" 2>&1
  rc=$?
  BATCH="$BATCH ${c}|${rc}|artifacts/regress_${c}.log"
  if [ $rc -eq 0 ]; then PASS=$((PASS+1)); echo "[$c] GREEN (rc=0)";
  else FAIL=$((FAIL+1)); FAILED="$FAILED $c"; echo "[$c] RED rc=$rc"; tail -5 artifacts/regress_${c}.log; echo "$c" >> artifacts/failed_cases.txt; fi
done
echo "=== REGRESSION SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
$PY harness/junit_report.py --batch artifacts/junit.xml $BATCH >/dev/null 2>&1 && echo "junit: artifacts/junit.xml"
exit $((FAIL > 0 ? 1 : 0))
