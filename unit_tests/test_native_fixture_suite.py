"""Validation of each compound fixture's required live initial project snapshot."""
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.native_fixture_suite import FIXTURE_CASES, child_id, verify_initial
from harness.script_verify import _InvalidEvidence


def test_fixture_children_have_stable_distinct_run_ids():
    first, second = FIXTURE_CASES
    batch = "abc123" * 5 + "45"
    assert child_id(batch, first) == child_id(batch, first)
    assert child_id(batch, first) != child_id(batch, second)
    assert child_id(batch, first) != child_id("e" * 32, first)


@pytest.mark.parametrize("name,value", [("layer_height", "0.24"), ("seam_position", "random"),
                                       ("ironing_type", "topmost")])
def test_initial_witness_rejects_preserved_state_drift(name, value):
    fixture = (Path(__file__).resolve().parents[1] / LAYER_FIXTURE).read_bytes()
    verify_initial(fixture, fixture)
    changed = BytesIO()
    with ZipFile(BytesIO(fixture)) as source, ZipFile(changed, "w") as dest:
        for member in source.infolist():
            raw = source.read(member)
            if member.filename == "Metadata/project_settings.config":
                settings = json.loads(raw)
                settings[name] = value
                raw = json.dumps(settings).encode()
            dest.writestr(member, raw)
    with pytest.raises(_InvalidEvidence):
        verify_initial(changed.getvalue(), fixture)
