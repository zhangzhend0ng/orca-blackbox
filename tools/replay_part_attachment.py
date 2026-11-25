"""Re-evaluate the attachment and group-movement geometry from a #249 harvest."""
import json
import sys
from pathlib import Path

from tools.replay_evidence_files import verified_part

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from part_attachment_oracle import verify_attachment, verify_group_move


def replay(directory: Path, prefix: str) -> dict:
    manifest = json.loads((directory / f"{prefix}-object_artifacts.json").read_text(encoding="utf-8-sig"))
    original, part, added = (
        verified_part(directory, prefix, manifest, name)
        for name in ("original.3mf", "part.stl", "added.3mf")
    )
    attachment = verify_attachment(original, added, part)
    checks = {"attached_positive_mesh_matches_stl": True, "both_parts_move_with_parent": False,
              "unchanged_move_rejected": False}
    result = {"attachment": attachment, "checks": checks}
    try:
        verify_group_move(added, added)
    except ValueError:
        checks["unchanged_move_rejected"] = True
    if not any(entry["part"] == "moved.3mf" for entry in manifest):
        result["missing"] = "moved.3mf"
        return result
    moved = verified_part(directory, prefix, manifest, "moved.3mf")
    result["group_move"] = verify_group_move(added, moved)
    checks["both_parts_move_with_parent"] = True
    return result
