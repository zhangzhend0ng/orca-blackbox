"""Recalculate the plate layout checks from the harvested GUI project files."""

import json
from hashlib import sha256
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
    parts = {part["part"] for part in manifest}
    before = read("before.3mf")
    if "cloned.3mf" not in parts:
        from delete_object_oracle import objects

        return {"checks": {"initial_fixture_retained": objects(before) == objects(read("fixture.3mf")),
                           "clone_evidence_present": False, "fill_evidence_present": False}}
    filled = read("filled.3mf") if "filled.3mf" in parts else None
    result = verify_clone(before, read("cloned.3mf"), filled)
    if filled is None:
        result["checks"]["fill_evidence_present"] = False
    return result


def replay_delete_plate(directory: Path, prefix: str) -> dict:
    from plate_reserve_oracle import verify_delete_plate

    _, read = _projects(directory, prefix)
    result = verify_delete_plate(read("before.3mf"), read("after.3mf"))
    return {"checks": {"deleted_selected_plate_and_preserved_objects": True}, "plate_membership": result}


def replay_split(directory: Path, prefix: str) -> dict:
    from plate_reserve_oracle import verify_split, verify_split_selection

    manifest, read = _projects(directory, prefix)
    split = read("split.3mf")
    result = {"checks": {"shell_geometry_preserved": True},
              "shells": verify_split(read("before.3mf"), split)}
    stages = {"left-color.3mf", "both-colors.3mf"}
    result["checks"]["independent_selection_and_coloring"] = False
    if stages <= {part["part"] for part in manifest}:
        result["filaments"] = verify_split_selection(
            split, read("left-color.3mf"), read("both-colors.3mf"))
        result["checks"]["independent_selection_and_coloring"] = True
    return result


def replay_stl_viewer(directory: Path, prefix: str) -> dict:
    from plate_reserve_oracle import verify_f3d_image, verify_stl

    manifest, read = _projects(directory, prefix)
    exported = read("selected-object.stl")
    result = {"checks": {"complete_stl_geometry": True, "independent_viewer": False},
              "stl": verify_stl(read("before.3mf"), exported)}
    required = {"f3d-version.log", "f3d-view.log", "f3d-invalid.log", "f3d-view.png", "invalid.stl"}
    parts = {part["part"] for part in manifest}
    if not required <= parts:
        return result
    for name in required:
        read(name)
    analysis = json.loads(read("analysis.json").read_text(encoding="utf-8-sig"))
    viewer = analysis["viewer"]
    rendered = read("f3d-view.png")
    result["render"] = verify_f3d_image(rendered)
    result["checks"]["independent_viewer"] = (
        "f3d" in read("f3d-version.log").read_text(encoding="utf-8", errors="replace").casefold()
        and viewer["positive_rc"] == 0 and viewer["negative_rejected"] is True
        and sha256(exported.read_bytes()).hexdigest() == viewer["source_sha256"]
        and sha256(rendered.read_bytes()).hexdigest() == viewer["output_sha256"]
    )
    if "f3d-invalid.png" in parts:
        negative_image = read("f3d-invalid.png")
        try:
            verify_f3d_image(negative_image)
        except (OSError, ValueError):
            pass
        else:
            result["checks"]["independent_viewer"] = False
    return result
