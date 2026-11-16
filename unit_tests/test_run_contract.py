"""Pure data tests; no GUI and no host-regression evidence."""
import copy
import json

import pytest

from harness.run_contract import ContractError, load_contract, validate_contract


@pytest.fixture
def contract_data():
    return {"schema_version": 1, "case_id": "m0_boot_check", "contract_version": "1",
            "executor": "script", "required_checks": ["path", "business"],
            "steps": [{"id": "boot", "goal": "Launch from GUI"}],
            "limits": {"timeout_s": 120, "max_actions": 20,
                       "max_retries": 0, "max_cost_usd": 0}}


def test_contract_freezes_input_and_serializes_independent_copy(contract_data):
    frozen = validate_contract(contract_data)
    before = copy.deepcopy(contract_data)
    contract_data["steps"][0]["goal"] = "mutated"
    exported = frozen.to_dict()
    assert exported == before
    exported["required_checks"].clear()
    assert frozen.required_checks == ("path", "business")


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("case_id", "../escape"),
    ("executor", "shell"), ("required_checks", []),
    ("required_checks", ["path", "path"]), ("required_checks", [None]),
    ("steps", []), ("steps", [{"id": "x", "goal": ""}]),
    ("steps", [{"id": "x", "goal": "ok", "command": "shell"}]),
], ids=["bool-version", "future-version", "path-id", "executor", "empty-checks",
        "duplicate-checks", "check-type", "empty-steps", "blank-goal", "unknown-step"])
def test_invalid_contract_is_rejected(contract_data, field, value):
    contract_data[field] = value
    with pytest.raises(ContractError):
        validate_contract(contract_data)


@pytest.mark.parametrize("field,value", [
    ("timeout_s", True), ("timeout_s", 0), ("max_actions", 0),
    ("max_retries", -1), ("max_cost_usd", True),
    ("max_cost_usd", float("nan")), ("max_cost_usd", float("inf")),
])
def test_limits_reject_wrong_types_and_unbounded_values(contract_data, field, value):
    contract_data["limits"][field] = value
    with pytest.raises(ContractError, match="limits"):
        validate_contract(contract_data)


def test_unknown_top_field_and_duplicate_step_rejected(contract_data):
    contract_data["extra"] = "not allowed"
    with pytest.raises(ContractError, match="fields"):
        validate_contract(contract_data)
    contract_data.pop("extra")
    contract_data["steps"] *= 2
    with pytest.raises(ContractError, match="duplicate"):
        validate_contract(contract_data)


@pytest.mark.parametrize("content", [
    '{"schema_version":1,"schema_version":1}', '{"value":NaN}',
    '[' * 2000 + ']' * 2000, '\ufeff{}', '{' + ' ' * 65536 + '}',
], ids=["duplicate-json-key", "nonfinite-json", "deep-json", "bom", "size"])
def test_load_rejects_unsafe_or_excessive_json(tmp_path, content):
    path = tmp_path / "contract.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ContractError):
        load_contract(path)


def test_load_valid_json(tmp_path, contract_data):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract_data), encoding="utf-8")
    assert load_contract(path).case_id == "m0_boot_check"
