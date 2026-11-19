from collections import Counter

from harness.native_pairwise import PAIR_CASES, admitted, expected_settings
from harness.native_save_session import native_contract, native_spec
from harness.native_uia_replay import read_recipe
from harness.run_verdict import contract_digest


def test_generates_legal_unordered_pairs_plus_move_layer_reverse():
    coverage = Counter(frozenset(order) for order in PAIR_CASES.values())
    assert len(coverage) == 6
    assert coverage[frozenset(("layer", "move"))] == 2
    assert all(admitted(order) for order in PAIR_CASES.values())
    assert not admitted(("ironing", "layer"))
    assert not admitted(("ironing", "seam"))


def test_generated_contracts_bind_order_and_source_segments():
    digests = set()
    for scenario, order in PAIR_CASES.items():
        recipe, digest = read_recipe(scenario)
        assert tuple(segment["operation"] for segment in recipe["segments"]) == order
        assert sum(step["tool"] == "Shortcut" for step in recipe["steps"]) == 1
        contract = native_contract("script", scenario)
        assert digest in contract.steps[0].goal
        assert native_spec(contract_digest(contract)) == ("script", scenario)
        digests.add(digest)
    assert len(digests) == len(PAIR_CASES)
    assert expected_settings("pair_layer_ironing") == {"layer_height": "0.24", "ironing_type": "topmost"}
