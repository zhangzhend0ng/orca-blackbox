"""Recheck the three exported project states from a verified #248 guest run."""
import json
import sys
from pathlib import Path

from tools.replay_evidence_files import verified_part

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from delete_object_oracle import objects, verify_sequence


def replay(directory: Path, prefix: str) -> dict:
    manifest = json.loads((directory / f'{prefix}-object_artifacts.json').read_text(encoding='utf-8-sig'))
    fixture, before, deleted, restored = (
        verified_part(directory, prefix, manifest, name)
        for name in ('Alpha-Bravo.3mf', 'before.3mf', 'deleted.3mf', 'restored.3mf')
    )
    bounds = verify_sequence(before, deleted, restored)
    try:
        verify_sequence(before, before, restored)
    except ValueError:
        unchanged_rejected = True
    else:
        unchanged_rejected = False
    return {'checks': {'fixture_loaded': objects(fixture) == objects(before), 'only_alpha_removed_and_restored': True,
                       'unchanged_project_rejected': unchanged_rejected}, 'world_bounds_mm': bounds}
