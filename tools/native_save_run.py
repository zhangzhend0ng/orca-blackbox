"""Fixed guest composition entry, launched only by hv_go."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    from harness.native_save_session import run_native_save
    result = run_native_save(args.run_id)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result.get("verified_pass") else 1)
