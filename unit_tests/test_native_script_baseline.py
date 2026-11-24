from types import SimpleNamespace

import pytest

from harness.agent_protocol import LAYER_FIXTURE_SHA256, MODEL_FIXTURES, STD_FIXTURE_SHA256
from harness.native_matrix import (SCRIPT_COMPARISON_SCENARIOS, UIA_HYBRID_SCENARIOS,
    UIA_LAYER_SCENARIO, UIA_LAYER_STRENGTH_SCENARIO, scenario_spec)
from harness.native_save_session import NativeSaveExecutor, native_contract, native_spec
from harness.native_script_baseline import edit_layer, edit_param_layer_pair, edit_project
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

    ui = SimpleNamespace(app=SimpleNamespace(hwnd=1), boot_details={"fixture_sha256": LAYER_FIXTURE_SHA256},
                         wu=SimpleNamespace(client_to_screen=lambda *args: (10, 20)),
                         wait=lambda condition, _: condition(), owned=lambda hwnd: hwnd in {3, 4}, edit=edit)
    assert scenario_spec("script", UIA_LAYER_SCENARIO) == ("Quality", None)
    edit_layer(ui)
    assert calls == [(270, 730, "0.24")]
    ui.edit = lambda *args, **_kwargs: {"target_hwnd": 4, "after_text": "0.24"}
    with pytest.raises(ValueError, match="script_layer_readback"):
        edit_layer(ui)


# ---- the two height fields start at the fixture's own pair (#254) -----------------

CUBE, STD = LAYER_FIXTURE_SHA256, STD_FIXTURE_SHA256
ROWS = ((260, 740, 300, 760), (260, 770, 300, 790))     # layer height, first layer height


def _fields(monkeypatch, values, *, fixture=CUBE, reads=None):
    """(ui, calls) for a run opened on `fixture` whose Quality page shows the two
    height fields reading `values`. `reads` replays what each look at the page shows
    (the last look repeats). `edit` answers the hwnd typed into and the text it left
    there, as the real receipt does; `calls` is every (x, y, text) typed."""
    looks = list(reads or [values])
    seen = [0]

    def page(_app):
        shown = looks[min(seen[0], len(looks) - 1)]
        seen[0] += 1
        return [(rect, 3 + index, value) for index, (rect, value) in enumerate(zip(ROWS, shown))]

    monkeypatch.setattr("harness.process_panel.float_edits_in_view", page)
    calls = []

    def edit(x, y, text):
        calls.append((x, y, text))
        index = [i for i, rect in enumerate(ROWS) if (rect[1] + rect[3]) // 2 - 20 == y]
        assert len(index) == 1, "a point that is no height field"
        return {"target_hwnd": 3 + index[0], "after_text": text, "committed": True}

    ui = SimpleNamespace(app=SimpleNamespace(hwnd=1), boot_details={"fixture_sha256": fixture},
                         wu=SimpleNamespace(client_to_screen=lambda *_args: (10, 20)),
                         wait=lambda condition, _: condition(), owned=lambda hwnd: hwnd in {3, 4},
                         edit=edit, main_input=lambda: None, pause=lambda _seconds: None)
    return ui, calls


def test_layer_pair_on_the_cube_types_both_fields_and_returns_the_receipt(monkeypatch):
    ui, calls = _fields(monkeypatch, ("0.4", "0.40"), reads=[("0.4", "0.40"), ("0.2", "0.40")])
    receipt = edit_param_layer_pair(ui)
    assert calls == [(270, 730, "0.2"), (270, 760, "0.25")]
    assert receipt["fixture_sha256"] == CUBE
    assert receipt["entry_read"] == ["0.4", "0.40"] and receipt["start_expected"] == ["0.4", "0.4"]
    assert receipt["layer_height"]["after_text"] == "0.2"
    assert receipt["initial_layer_print_height"]["after_text"] == "0.25"


@pytest.mark.parametrize("fixture", [STD, MODEL_FIXTURES["_sphere"][1], MODEL_FIXTURES["_boat"][1]])
def test_layer_pair_enters_on_the_precondition_pair_and_types_it_again(monkeypatch, fixture):
    # 0.20 + 0.25 is what these fixtures already hold; the entry check demanded
    # the cube's 0.4 (script_layer_fields_not_as_expected). Both fields are typed.
    ui, calls = _fields(monkeypatch, ("0.2", "0.25"), fixture=fixture)
    receipt = edit_param_layer_pair(ui)
    assert calls == [(270, 730, "0.2"), (270, 760, "0.25")]
    assert receipt["entry_read"] == ["0.2", "0.25"] and receipt["start_expected"] == ["0.2", "0.25"]


@pytest.mark.parametrize("fixture, shown", [(STD, ("0.4", "0.4")), (CUBE, ("0.2", "0.25")),
                                            (STD, ("0.2", "0.3")), (STD, ("0.2", "abc"))])
def test_layer_pair_refuses_fields_that_do_not_read_their_fixture(monkeypatch, fixture, shown):
    ui, calls = _fields(monkeypatch, shown, fixture=fixture)
    with pytest.raises(ValueError, match="script_layer_fields_not_as_expected"):
        edit_param_layer_pair(ui)
    assert calls == []


def test_layer_pair_requires_the_first_layer_field_untouched_between_the_edits(monkeypatch):
    ui, calls = _fields(monkeypatch, ("0.4", "0.4"), reads=[("0.4", "0.4"), ("0.2", "0.2")])
    with pytest.raises(ValueError, match="param_layer_pair_initial_field"):
        edit_param_layer_pair(ui)
    assert calls == [(270, 730, "0.2")]


def test_layer_driver_refuses_a_fixture_whose_pair_is_not_registered(monkeypatch):
    ui, calls = _fields(monkeypatch, ("0.4", "0.4"), fixture="0" * 64)
    with pytest.raises(ValueError, match="script_layer_fixture_unregistered"):
        edit_layer(ui)
    assert calls == []


def test_every_registered_fixture_pair_is_the_one_its_file_was_saved_with():
    from hashlib import sha256
    from pathlib import Path
    from harness.agent_protocol import FIXTURE_SUFFIXES, LAYER_FIXTURE, LAYER_FIELDS_BY_FIXTURE
    from harness.project_3mf import _settings

    rows = [(LAYER_FIXTURE, LAYER_FIXTURE_SHA256)] + list(FIXTURE_SUFFIXES.values())
    assert {digest for _path, digest in rows} == set(LAYER_FIELDS_BY_FIXTURE)
    for path, digest in rows:
        raw = (Path(__file__).resolve().parents[1] / path).read_bytes()
        assert sha256(raw).hexdigest() == digest
        saved = _settings(raw, lambda: False)
        assert LAYER_FIELDS_BY_FIXTURE[digest] == (saved["layer_height"], saved["initial_layer_print_height"])


def test_strength_perturbation_uses_the_same_goal_and_navigates_to_quality(monkeypatch):
    changed = UIA_LAYER_STRENGTH_SCENARIO
    assert changed in UIA_HYBRID_SCENARIOS
    assert scenario_spec("script", changed) == scenario_spec("zcode", changed) == ("Strength", None)
    from harness.native_pilots import business_goal
    assert business_goal(changed) == business_goal(UIA_LAYER_SCENARIO)
    calls = []
    ui = SimpleNamespace(
        named_child=lambda name: calls.append(name) or ("Quality", [1, 2, 3, 4], 5),
        click_rect=lambda rect: calls.append(rect),
        wait=lambda predicate, _: predicate(),
        pause=lambda _: None,
    )
    monkeypatch.setattr("harness.native_script_baseline.edit_layer", lambda ui: calls.append("edit"))
    edit_project(ui, changed, None)
    assert calls == ["Quality", [1, 2, 3, 4], "edit"]
    calls.clear()
    edit_project(ui, UIA_LAYER_SCENARIO, None)
    assert calls == ["edit"]
