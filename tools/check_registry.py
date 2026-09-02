"""tools/check_registry.py — registry consistency self-check (no deps).

Validates that cases.py stays the single source of truth:
1. every registry entry's file exists and its stem == the key;
2. the file actually looks like a case script (m<digit>* naming);
3. the summary matches the script's line-2 header comment ("# <stem>.py — ...");
4. run_regression.sh contains NO hardcoded case list (reads cases.py);
5. runner/hv_go.ps1 contains NO hardcoded case list;
6. no case script on disk is missing from the registry (m<digit>* only —
   diag_* and _CASE_SKIP helpers are intentionally outside).

Exit 0 = PASS; non-zero with a diff = FAIL.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cases import CASES, enabled_cases  # noqa: E402

_SKIP = {"m3_common.py", "m5_common.py"}

problems: list[str] = []


def check(msg_ok: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {msg_ok}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        problems.append(f"{msg_ok}: {detail}")


# 1+2: files exist, stem == key, case naming
for key, meta in CASES.items():
    f = ROOT / meta["file"]
    check(f"file exists: {meta['file']}", f.exists())
    check(f"stem==key: {key}", Path(meta["file"]).stem == key)
    check(f"case naming: {key}", bool(re.match(r"^m\d", key)) or key.startswith("diag_"))

# 3: summary extractable from the script's line-2 header comment
for key in CASES:
    s = __import__("cases").summary(key)
    check(f"summary extractable: {key}", bool(s), "no '# <stem>.py — ...' header in first 5 lines")

# 4+5: no hardcoded lists in batch entries
sh = (ROOT / "run_regression.sh").read_text(encoding="utf-8")
check("run_regression.sh reads cases.py", "from cases import enabled_cases" in sh)
check("run_regression.sh has no hardcoded m-case list",
      not re.search(r"CASES=[\"']m\w", sh.replace("CASES=$(", "")))
ps1 = (ROOT / "runner" / "hv_go.ps1").read_text(encoding="utf-8")
check("hv_go.ps1 reads cases.py", "from cases import enabled_cases" in ps1)
check("hv_go.ps1 has no hardcoded case array",
      not re.search(r"@\(?\s*'m\w+_'\s*,", ps1))

# 6: no orphan case scripts outside the registry
on_disk = {p.name for p in (ROOT / "tests").glob("m*.py")
           if re.match(r"^m\d", p.name) and p.name not in _SKIP}
in_reg = {Path(meta["file"]).name for meta in CASES.values()}
orphans = on_disk - in_reg
check("no unregistered case scripts in tests/", not orphans, f"orphans={sorted(orphans)}")
check("registry files live under tests/",
      all(meta["file"].startswith("tests/") for meta in CASES.values()))

# 7: sanity of the canonical suite
reg = enabled_cases("regression")
check("regression suite non-empty (36 expected)", len(reg) == 36, f"got {len(reg)}")

print(f"\nregistry: {len(CASES)} entries | regression={len(reg)} "
      f"smoke={len(enabled_cases('smoke'))} "
      f"other={len(CASES) - len(reg) - len(enabled_cases('smoke'))}")
print("CHECK_REGISTRY: PASS" if not problems else f"CHECK_REGISTRY: FAIL ({len(problems)})")
sys.exit(1 if problems else 0)
