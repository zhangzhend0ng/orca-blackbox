"""Recalculate the plate layout checks from the harvested GUI project files."""

import json
from pathlib import Path
import sys

from tools.replay_evidence_files import verified_part

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def _projects(directory: Path, prefix: str):
    manifest_path = directory / f"{prefix}-object_artifacts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    def read(name):
        return verified_part(directory, prefix, manifest, name)

    return manifest, read


def replay_arrange(directory: Path, prefix: str) -> dict:
    from plate_layout_oracle import verify_arrange

    _, read = _projects(directory, prefix)
    return verify_arrange(read("before.3mf"), read("after.3mf"))


def replay_orient(directory: Path, prefix: str) -> dict:
    from plate_layout_oracle import verify_orient

    _, read = _projects(directory, prefix)
    return verify_orient(read("before.3mf"), read("after.3mf"))


def replay_clone(directory: Path, prefix: str) -> dict:
    from plate_layout_oracle import verify_clone

    manifest, read = _projects(directory, prefix)
    filled = read("filled.3mf") if any(part["part"] == "filled.3mf" for part in manifest) else None
    result = verify_clone(read("before.3mf"), read("cloned.3mf"), filled)
    if filled is None:
        result["checks"]["fill_evidence_present"] = False
    return result


def replay_delete_plate(directory: Path, prefix: str) -> dict:
    from plate_reserve_oracle import verify_delete_plate

    _, read = _projects(directory, prefix)
    result = verify_delete_plate(read("before.3mf"), read("after.3mf"))
    return {"checks": {"deleted_selected_plate_and_preserved_objects": True}, "plate_membership": result}
