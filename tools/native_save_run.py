"""Fixed guest composition entry, launched only by hv_go."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--actor", choices=("codex", "zcode", "script"), default="codex")
    from harness.native_matrix import scenario_names
    p.add_argument("--scenario", choices=scenario_names(), default="base")
    args = p.parse_args()
    from harness.native_save_session import run_native_save
    result = run_native_save(args.run_id, args.actor, args.scenario)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result.get("verified_pass") else 1)
