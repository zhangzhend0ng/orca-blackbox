from copy import deepcopy

import pytest

from harness.native_save_session import contract_digest, native_contract, native_spec
from harness.native_uia_replay import executable_steps, read_recipe, verify_recipe


def test_recorded_script_uses_registered_scope_and_fresh_output_path():
    recipe, digest = read_recipe()
    output = r"C:\runs\new\projects\0001.3mf"
    steps = list(executable_steps(recipe, output))
    assert steps[1][1]["text"] == "0.24"
    assert steps[5][1]["text"] == output
    assert all("loc" not in args and "hwnd" not in args for _, args in steps)
    contract = native_contract("script", "uia_replay_layer")
    assert any(digest in step["goal"] for step in contract.to_dict()["steps"])
    assert native_spec(contract_digest(contract)) == ("script", "uia_replay_layer")
    with pytest.raises(ValueError):
        native_contract("zcode", "uia_replay_layer")


@pytest.mark.parametrize("change", ("coordinates", "original_path", "extra_action", "wrong_value"))
def test_replay_does_not_admit_untrusted_operations(change):
    recipe = deepcopy(read_recipe()[0])
    if change == "coordinates":
        recipe["steps"][6]["arguments"]["loc"] = [20, 30]
    elif change == "original_path":
        recipe["steps"][5]["arguments"]["text"] = r"C:\old.3mf"
    elif change == "extra_action":
        recipe["steps"].insert(1, {"tool": "Screenshot", "arguments": {"region_name": "wx_sidebar"}})
    else:
        recipe["steps"][1]["arguments"]["text"] = "0.26"
    with pytest.raises(ValueError):
        verify_recipe(recipe)
