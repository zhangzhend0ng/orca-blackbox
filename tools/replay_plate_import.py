"""Recheck Feishu #244's printer precondition, STL geometry and run-specific source."""
import json
from pathlib import Path, PureWindowsPath
import sys

from tools.replay_evidence_files import verified_part

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from import_model_oracle import selected_printer, verify_import


def replay(directory: Path, prefix: str) -> dict:
    manifest = json.loads((directory / f"{prefix}-object_artifacts.json").read_text(encoding="utf-8-sig"))
    template, imported, source, analysis_path = (
        verified_part(directory, prefix, manifest, name)
        for name in ("new-project.3mf", "imported.3mf", "cube_20mm.stl", "analysis.json")
    )
    analysis = json.loads(analysis_path.read_text(encoding="utf-8-sig"))
    initial = selected_printer(template)
    saved = verify_import(imported, source)
    log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    marker = "[m7x244] retained work directory: "
    run_dirs = [line.removeprefix(marker) for line in log.splitlines() if line.startswith(marker)]
    entered = PureWindowsPath(analysis["chooser"]["entered"])
    matches = len(run_dirs) == 1 and entered == PureWindowsPath(run_dirs[0]) / "cube_20mm.stl"
    try:
        verify_import(template, source)
    except ValueError:
        original_rejected = True
    else:
        original_rejected = False
    return {
        "checks": {
            "selected_printer_before_and_after": initial["model"] == saved["printer"]["model"],
            "chooser_and_saved_mesh_reference_this_run": matches and entered == PureWindowsPath(saved["source_file"]),
            "original_project_rejected_as_import_result": original_rejected,
        },
        "initial_printer": initial,
        "import": saved,
    }
