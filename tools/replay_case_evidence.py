"""Replay the on-disk assertions of a harvested GUI case.

Pass one or more *-receipt.json files. JSON output and exit status describe the
offline checks, including their negative controls. The original GUI verdict is
reported independently and is never updated.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import replay_delete_object, replay_negative_part, replay_part_attachment, replay_plate_context, replay_plate_import, replay_plate_layout, replay_project_save
from tools import replay_sphere_layer_pair


ADAPTERS = {
    "m7x_201_save_project_reopen": replay_project_save.replay,
    "m7x_239_delete_all": replay_plate_context.replay_delete_all,
    "m7x_240_arrange": replay_plate_layout.replay_arrange,
    "m7x_241_orient": replay_plate_layout.replay_orient,
    "m7x_242_delete_plate": replay_plate_layout.replay_delete_plate,
    "m7x_243_add_primitive": replay_plate_context.replay_add_primitive,
    "m7x_244_add_model": replay_plate_import.replay,
    "m7x_245_clone_fill": replay_plate_layout.replay_clone,
    "m7x_247_split_shells": replay_plate_layout.replay_split,
    "m7x_248_delete_object": replay_delete_object.replay,
    "m7x_249_add_part": replay_part_attachment.replay,
    "m7x_250_negative_part": replay_negative_part.replay,
    "m7x_252_export_stl_viewer": replay_plate_layout.replay_stl_viewer,
    "m7x_254_sphere_layer_pair": replay_sphere_layer_pair.replay,
}


def replay_receipt(path: Path) -> dict:
    started = perf_counter()
    report = {"receipt": str(path), "offline_checks_passed": False}
    try:
        suffix = "-receipt.json"
        if not path.name.endswith(suffix):
            raise ValueError(f"expected a *{suffix} filename")
        if not __debug__:
            raise ValueError("run without -O so the GUI oracle's assertions are active")
        prefix = path.name.removesuffix(suffix)
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
        case = receipt["case"]
        if case not in ADAPTERS:
            raise ValueError(f"unsupported case: {case}")
        report.update(case=case, commit=receipt["commit"], historical_summary=receipt["summary"])
        dispatched = datetime.fromisoformat(receipt["dispatched_at"])
        completed = datetime.fromisoformat(receipt["scenario_completed_at"])
        report["historical_scenario_seconds"] = round((completed - dispatched).total_seconds(), 3)
        log = path.with_name(f"{prefix}-case.log")
        if hashlib.sha256(log.read_bytes()).hexdigest() != receipt["log_sha256"].lower():
            raise ValueError("case.log: SHA-256 differs from receipt")
        result = ADAPTERS[case](path.parent, prefix)
        report["result"] = result
        checks = result["checks"]
        report["offline_checks_passed"] = bool(checks) and all(v is True for v in checks.values())
    except (OSError, ValueError, LookupError, TypeError, AttributeError, ArithmeticError,
            AssertionError, BadZipFile, ParseError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["offline_seconds"] = round(perf_counter() - started, 6)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs="+")
    args = parser.parse_args()
    reports = [replay_receipt(path) for path in args.receipts]
    print(json.dumps(reports, indent=2))
    return 0 if all(report["offline_checks_passed"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
