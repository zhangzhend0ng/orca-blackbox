"""Synthetic checks for the Feishu #254 layer-pair oracle (settings scope only).

The G-code schedule half needs real sliced output and is proven on the
guest; these tests pin the change-scope whitelist and the value gates."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.script_verify import _InvalidEvidence
from harness.pilot_common import LAYER_PAIR, inspect_preserved_settings


def _settings(**overrides):
    base = {"layer_height": "0.4", "initial_layer_print_height": "0.4", "wall_loops": "2"}
    base.update(overrides)
    return base


def test_layer_pair_scope_accepts_exactly_the_two_changes():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.25")
    inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)


def test_layer_pair_scope_rejects_an_extra_changed_key():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.25", wall_loops="3")
    with pytest.raises(_InvalidEvidence) as err:
        inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)
    assert "pilot_unrelated_setting_changed" in str(err.value)


def test_layer_pair_scope_rejects_wrong_target_value():
    actual = _settings(layer_height="0.2", initial_layer_print_height="0.3")
    with pytest.raises(_InvalidEvidence):
        inspect_preserved_settings(actual, _settings(), allowed_changes=LAYER_PAIR)


def test_layer_pair_values_are_the_registered_combination():
    assert LAYER_PAIR == {"layer_height": "0.2", "initial_layer_print_height": "0.25"}
