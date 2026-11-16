"""Validate, initialize, or smoke-test the v3 runtime; never drive GUI.

This is a recording primitive, not a regression runner or a release gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.run_contract import load_contract
from harness.run_evidence import RunEvidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "init", "smoke"))
    parser.add_argument("contract", type=Path, nargs="?")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts" / "v3")
    args = parser.parse_args(argv)
    if args.command == "smoke" and args.contract is not None:
        parser.error("smoke uses its built-in synthetic task; do not supply a contract")
    if args.command != "smoke" and args.contract is None:
        parser.error("validate and init require a contract file")
    try:
        if args.command == "smoke":
            from harness.runtime_smoke import run_smoke
            result = run_smoke(args.root)
        else:
            contract = load_contract(args.contract)
            if args.command == "validate":
                result = {"status": "valid", "case_id": contract.case_id}
            else:
                args.root.mkdir(parents=True, exist_ok=True)
                with RunEvidence.create(args.root, contract) as writer:
                    result = {"status": "initialized", "run_id": writer.run_id,
                              "run_dir": str(writer.run_dir), "gui_executed": False}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if args.command != "smoke" or result.get("verified_pass") is True else 1
    except (ValueError, OSError) as exc:
        # Do not echo contract payloads or filesystem exception strings: either
        # can contain user data. The exception type is enough for CLI diagnosis.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
