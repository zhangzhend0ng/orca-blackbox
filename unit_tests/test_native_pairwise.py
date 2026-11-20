from collections import Counter

from harness.native_pairwise import CONFIG_CASES, CONFIG_PLAN, LEGACY_PAIRS, admitted, expected_settings
from harness.native_config_cases import value_pairs
from harness.native_save_session import native_contract, native_spec
from harness.native_uia_replay import read_recipe
from harness.run_verdict import contract_digest


def test_generates_legal_unordered_pairs_plus_move_layer_reverse():
    coverage = Counter(frozenset(order) for order in LEGACY_PAIRS.values())
    assert len(coverage) == 6
    assert coverage[frozenset(("layer", "move"))] == 2
    assert all(admitted(order) for order in LEGACY_PAIRS.values())
    assert not admitted(("ironing", "layer"))
    assert not admitted(("ironing", "seam"))


def test_generated_contracts_bind_order_and_source_segments():
    digests = set()
    for scenario, order in LEGACY_PAIRS.items():
        recipe, digest = read_recipe(scenario)
        assert tuple(segment["operation"] for segment in recipe["segments"]) == order
        assert sum(step["tool"] == "Shortcut" for step in recipe["steps"]) == 1
        contract = native_contract("script", scenario)
        assert digest in contract.steps[0].goal
        assert native_spec(contract_digest(contract)) == ("script", scenario)
        digests.add(digest)
    assert len(digests) == len(LEGACY_PAIRS)
    assert expected_settings("pair_layer_ironing") == {"layer_height": "0.24", "ironing_type": "topmost"}


def test_value_pairs_checked_independently_of_recording_order():
    plan = CONFIG_PLAN["legal"]
    selected = [row for row in plan if row["selection"] == "selected"]
    assert len(selected) == 4
    assert len(set().union(*(value_pairs(row["values"]) for row in selected))) == 12
    assert any(row["order"] == () for row in selected)
    excluded = [row for row in plan if row["selection"] == "excluded"]
    assert len(excluded) == 4
    assert all(row["values"]["layer_height"] == "0.9" and row["rules"] == ["validate-layer-nozzle"]
               for row in excluded)
    assert any(not route["admitted"] for row in selected for route in row["orders"])


def test_generated_configs_bind_the_catalog_and_independent_business_contract():
    for scenario, row in CONFIG_CASES.items():
        recipe, digest = read_recipe(scenario)
        assert recipe["config_case"] == row
        assert recipe["checkpoints"][1]["visible"] is False
        contract = native_contract("script", scenario)
        assert digest in contract.steps[0].goal
        assert native_spec(contract_digest(contract)) == ("script", scenario)
