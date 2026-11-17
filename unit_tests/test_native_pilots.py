"""Business experiments are finite, isolated contracts, not stability passes."""
from dataclasses import replace
import hashlib
import json

import pytest

from harness.native_matrix import BUSINESS, SCENARIOS
from harness.native_pilots import PILOTS, business_goal, pilot_module
from harness.native_save_session import native_contract, native_spec
from harness.run_verdict import contract_digest
from unit_tests.test_native_save import native_evidence


def test_pilots_leave_existing_stability_denominator_and_legacy_contracts_unchanged():
    assert len(BUSINESS) == 8 and not (set(BUSINESS) & set(PILOTS))
    assert contract_digest(native_contract()) == "ee2dd9ed8b78898962450b9f3c540ad41ad8e19196ce8bc4ef3f25a7d33e2517"
    assert contract_digest(native_contract("zcode")) == "63877b2dd26fa6564e843c32cba40c5cc4e54cd940f3c18b412c1c55e21c938c"


@pytest.mark.parametrize("scenario", tuple(PILOTS))
def test_registered_business_identity_binds_goal_and_checker(scenario):
    contract = native_contract("zcode", scenario)
    assert native_spec(contract_digest(contract)) == ("zcode", scenario)
    assert contract.case_id == pilot_module(scenario).CASE_ID
    assert business_goal(scenario) in contract.steps[1].goal
    assert contract.limits.max_actions == 40 and contract.limits.max_retries == 0
    with pytest.raises(ValueError):
        native_contract("codex", scenario)
    with pytest.raises(ValueError):
        native_spec(contract_digest(replace(contract, case_id="other")))


@pytest.mark.parametrize("name", ["os", "../pilot_strength", "pilot_unregistered"])
def test_unregistered_goal_cannot_choose_a_module_or_checker(name):
    with pytest.raises(ValueError):
        pilot_module(name)
    with pytest.raises(ValueError):
        business_goal(name)


def test_known_missing_input_capability_blocks_before_a_process_can_start():
    from harness.native_pilots import require_pilot_ready
    from harness.native_save_session import NativeSaveExecutor
    with pytest.raises(RuntimeError, match="capability_blocked"):
        NativeSaveExecutor(contract_digest(native_contract("zcode", "pilot_transform")))
    require_pilot_ready("pilot_strength")
    require_pilot_ready("pilot_material")
    require_pilot_ready("quality_a")


@pytest.mark.parametrize("scenario", tuple(PILOTS))
@pytest.mark.parametrize("fault", [None, "host_contract", "wrong_business"])
def test_shared_custody_envelope_dispatches_only_the_bound_business_oracle(native_evidence, scenario, fault):
    from harness.native_save_session import verify_saved
    from unit_tests.test_pilot_strength import saved as strength_saved, sliced
    from unit_tests.test_pilot_material import saved as material_saved, tool1
    from unit_tests.test_pilot_transform import project as moved, moves
    snapshot = native_evidence
    root = snapshot.artifact_dir
    fixture = (root/"input/fixture.3mf").read_bytes()
    products = {
        "pilot_strength": (strength_saved(fixture), sliced()),
        "pilot_transform": (moved(), moves()),
        "pilot_material": (material_saved(fixture), tool1()),
    }
    project, gcode = products[scenario]
    if fault == "wrong_business":
        project, gcode = products["pilot_material" if scenario != "pilot_material" else "pilot_strength"]
    snapshot.contract = native_contract("zcode", scenario)
    digest = contract_digest(snapshot.contract)
    for name in ("projects/0001.3mf", "proof/0001.3mf"):
        (root/name).write_bytes(project)
    (root/"exports/0001.gcode").write_bytes(gcode)
    proof = json.loads((root/"proof.json").read_text())
    proof.update(contract_sha256=digest, project_sha256=hashlib.sha256(project).hexdigest(),
                 gcode_sha256=hashlib.sha256(gcode).hexdigest())
    (root/"proof.json").write_text(json.dumps(proof))
    host = json.loads((root/"host_done.json").read_text())
    host.update(actor="zcode", provider_id="new-provider", model_id="glm-5.3-flash",
                guard_checked=True, sources_unchanged=True, toolset_verified=True,
                scenario=scenario, contract_sha256=digest if fault != "host_contract" else "0"*64)
    (root/"host_done.json").write_text(json.dumps(host))
    trace = [json.loads(line) for line in (root/"native_trace.ndjson").read_text().splitlines()]
    for row in trace:
        row["started_at_ns"] = 80
    (root/"native_trace.ndjson").write_text("\n".join(json.dumps(row) for row in trace))
    png = b"synthetic setup frame; not GUI coverage"
    (root/"initial.png").write_bytes(png)
    (root/"setup.json").write_text(json.dumps({"run_id":snapshot.run_id, "scenario":scenario,
        "app_pid":123, "tab_clicked":"Quality", "finished_at_ns":70,
        "initial_sha256":hashlib.sha256(png).hexdigest()}))
    assert verify_saved(snapshot).evidence_complete is (fault is None)
