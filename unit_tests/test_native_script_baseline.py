from types import SimpleNamespace

import pytest

from harness.native_matrix import SCRIPT_COMPARISON_SCENARIOS, UIA_LAYER_SCENARIO, scenario_spec
from harness.native_save_session import NativeSaveExecutor, native_contract, native_spec
from harness.native_script_baseline import edit_layer
from harness.run_verdict import contract_digest


@pytest.mark.parametrize("scenario", SCRIPT_COMPARISON_SCENARIOS)
def test_script_comparison_has_separate_executor_and_shared_initial_state(scenario):
    script = native_contract("script", scenario)
    zcode = native_contract("zcode", scenario)
    assert scenario_spec("script", scenario) == scenario_spec("zcode", scenario)
    assert script.case_id == zcode.case_id
    assert script.executor == "script" and zcode.executor == "agent_mcp"
    assert script.required_checks == zcode.required_checks
    digest = contract_digest(script)
    assert digest != contract_digest(zcode)
    assert native_spec(digest) == ("script", scenario)
    assert NativeSaveExecutor(digest).kind == "script"


def test_script_comparison_is_not_available_for_arbitrary_native_scenarios():
    with pytest.raises(ValueError, match="native_script_scenario_not_registered"):
        native_contract("script", "uia_general_wall")


def test_layer_driver_converts_position_and_requires_target_and_readback(monkeypatch):
    edits = [((260, 740, 300, 760), 3, "0.4"), ((260, 770, 300, 790), 4, "0.40")]
    monkeypatch.setattr("harness.process_panel.float_edits_in_view", lambda app: edits)
    calls = []

    def edit(x, y, text):
        calls.append((x, y, text))
        return {"target_hwnd": 3, "after_text": "0.24"}

    ui = SimpleNamespace(app=SimpleNamespace(hwnd=1),
        wu=SimpleNamespace(client_to_screen=lambda *args: (10, 20)),
        wait=lambda condition, _: condition(), owned=lambda hwnd: hwnd in {3, 4}, edit=edit)
    assert scenario_spec("script", UIA_LAYER_SCENARIO) == ("Quality", None)
    edit_layer(ui)
    assert calls == [(270, 730, "0.24")]
    ui.edit = lambda *args: {"target_hwnd": 4, "after_text": "0.24"}
    with pytest.raises(ValueError, match="script_layer_readback"):
        edit_layer(ui)
