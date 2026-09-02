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
  $PY tests/${c}.py > artifacts/regress_${c}.log 2>&1
  rc=$?
  BATCH="$BATCH ${c}|${rc}|artifacts/regress_${c}.log"
  if [ $rc -eq 0 ]; then PASS=$((PASS+1)); echo "[$c] GREEN (rc=0)";
  else FAIL=$((FAIL+1)); FAILED="$FAILED $c"; echo "[$c] RED rc=$rc"; tail -5 artifacts/regress_${c}.log; echo "$c" >> artifacts/failed_cases.txt; fi
done
echo "=== REGRESSION SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
$PY harness/junit_report.py --batch artifacts/junit.xml $BATCH >/dev/null 2>&1 && echo "junit: artifacts/junit.xml"
exit $((FAIL > 0 ? 1 : 0))
