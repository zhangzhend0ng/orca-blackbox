"""Replay Feishu #201's saved-project and pre-reopen disk checks."""

import hashlib
import json
from pathlib import Path
import re

from harness.project_3mf import _archive, _geometry
from tools.replay_evidence_files import verified_part


MOVE_X_MM = 10
SAVE_SHA = re.compile(
    r"^  #201 File > Save Project rewrites the named file:[^\n]*, "
    r"sha256=([a-fA-F0-9]{64})\)$", re.MULTILINE,
)
REOPEN_SHA = re.compile(
    r"^\[m7x201\] editor exited:[^\n]*, pre-reopen SHA-256=([a-fA-F0-9]{64}),",
    re.MULTILINE,
)


def _expected_move(before_faces, before_matrix, after_faces, after_matrix):
    expected_matrix = (
        before_matrix[:9] + (before_matrix[9] + MOVE_X_MM,) + before_matrix[10:]
    )
    expected_faces = tuple(
        tuple((x + MOVE_X_MM, y, z) for x, y, z in face) for face in before_faces
    )
    return after_matrix == expected_matrix, after_faces == expected_faces


def _matches_logged_digest(pattern, case_log, digest):
    matches = pattern.findall(case_log)
    return len(matches) == 1 and matches[0].lower() == digest


def replay(directory: Path, prefix: str) -> dict:
    manifest = json.loads(
        (directory / f"{prefix}-project_artifacts.json").read_text(encoding="utf-8-sig")
    )
    case_log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    before = verified_part(directory, prefix, manifest, "before-save.3mf").read_bytes()
    after = verified_part(directory, prefix, manifest, "after-save.3mf").read_bytes()
    before_faces, _, before_matrix = _geometry(_archive(before, lambda: False))
    after_faces, _, after_matrix = _geometry(_archive(after, lambda: False))
    moved, translated_faces = _expected_move(before_faces, before_matrix, after_faces, after_matrix)
    saved_digest = hashlib.sha256(after).hexdigest()
    checks = {
        "saved_project_bytes_changed": before != after,
        "after_save_matches_logged_sha256": _matches_logged_digest(SAVE_SHA, case_log, saved_digest),
        "instance_moved_10_mm_along_x_only": moved,
        "world_triangles_translated_by_10_mm_along_x_only": translated_faces,
        "unchanged_geometry_rejected": _expected_move(
            before_faces, before_matrix, before_faces, before_matrix
        ) == (False, False),
        "opposite_direction_geometry_rejected": _expected_move(
            after_faces, after_matrix, before_faces, before_matrix
        ) == (False, False),
        "reopen_input_matches_saved_bytes_and_logged_sha256": False,
    }
    result = {
        "checks": checks,
        "before_translation_mm": [str(value) for value in before_matrix[9:]],
        "after_translation_mm": [str(value) for value in after_matrix[9:]],
        "triangle_count": len(after_faces),
        "after_save_sha256": saved_digest,
    }
    reopen_name = "reopen-input.3mf"
    if not any(part["part"] == reopen_name for part in manifest):
        result["reopen_input"] = "missing manifest entry"
        return result
    try:
        reopened = verified_part(directory, prefix, manifest, reopen_name).read_bytes()
    except FileNotFoundError:
        result["reopen_input"] = "missing snapshot"
        return result
    reopen_digest = hashlib.sha256(reopened).hexdigest()
    result["reopen_input_sha256"] = reopen_digest
    checks["reopen_input_matches_saved_bytes_and_logged_sha256"] = (
        reopened == after and _matches_logged_digest(REOPEN_SHA, case_log, reopen_digest)
    )
    return result
