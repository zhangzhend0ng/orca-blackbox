"""Geometry and contract failures the fixed cube tests cannot detect."""
from copy import deepcopy
from pathlib import Path

import pytest

from harness.model_move_pilot import (CATALOG, LAYER_FIXTURE, TEMPLATE, canonical, digest, instance,
                                      prepare_mesh, shape_digest, validate_plan)

REPO = Path(__file__).resolve().parents[1]


def test_geometry_input_changes_facts_and_digest_without_changing_template():
    carrier = (REPO / LAYER_FIXTURE).read_bytes()
    stl = (REPO / "fixtures/Prusa.stl").read_bytes()
    case = "0123456789abcdef0123456789abcdef"
    results = []
    for fmt, src in (("3mf", carrier), ("stl", stl)):
        prepared = prepare_mesh(src, fmt, carrier)
        plan = validate_plan({"run_id": case, "template": TEMPLATE, "source_sha256": "a" * 40,
            "prepared_sha256": digest(prepared), "import_policy": "geometry_in_fixed_process",
            "model": {"format": fmt, "name": f"arbitrary.{fmt}", "size": len(src), "sha256": digest(src)},
            "environment": CATALOG["sut"]}, case)
        points, faces, _ = instance(prepared, lambda: False)
        results.append((digest(canonical(plan)), shape_digest(points, faces, lambda: False), plan["template"]))
        bad = deepcopy(plan)
        bad["template"] = dict(plan["template"], target="ambiguous")
        with pytest.raises(ValueError, match="model_plan_identity"):
            validate_plan(bad, case)
    assert results[0][0] != results[1][0] and results[0][1] != results[1][1]
    assert results[0][2] == results[1][2]
