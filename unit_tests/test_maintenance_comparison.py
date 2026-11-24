import pytest
from harness.agent_protocol import MAINTENANCE_TRIALS, base_scenario, fixture_suffix
from harness.native_matrix import scenario_names, scenario_spec
from harness.native_pilots import native_fixture
from harness.native_save_policy import validate_input


@pytest.mark.parametrize("name", sorted(MAINTENANCE_TRIALS))
def test_same_fixture_and_initial_tab(name):
    case, suffix, tab = MAINTENANCE_TRIALS[name]
    assert name in scenario_names()
    assert base_scenario(name) == case
    assert fixture_suffix(name) == suffix
    assert native_fixture(name) == native_fixture(case + suffix)
    assert scenario_spec("script", name) == scenario_spec("zcode", name) == (tab, None)


@pytest.mark.parametrize("name, permitted, refused", [
    ("compare_276_strength", "700", "701"),
    ("compare_265_quality", "10%", "700"),
    ("base", "80", "700"),
])
def test_case_numeric_limits(name, permitted, refused):
    validate_input("Type", {"loc": [20, 20], "text": permitted}, "output", name)
    with pytest.raises(ValueError):
        validate_input("Type", {"loc": [20, 20], "text": refused}, "output", name)
