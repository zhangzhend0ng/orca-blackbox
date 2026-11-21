"""Exact serializer-equivalence rules for the frozen fixture/SUT pilots.

Only reviewed 2.3.6 -> 2.4.0 representation migrations are accepted. The
caller binds original bytes to LAYER_FIXTURE_SHA256 before this comparison.
"""
from .agent_verify import _require
from .gcode_check import config_value_all
from .native_pairwise import PAIR_CASES, expected_settings
from .script_verify import _check_cancel, _InvalidEvidence

_VECTOR_MIGRATIONS = frozenset("""
accel_to_decel_enable accel_to_decel_factor bridge_acceleration bridge_speed
default_acceleration default_jerk default_junction_deviation enable_overhang_speed
extrusion_rate_smoothing_external_perimeter_only gap_infill_speed infill_jerk
initial_layer_acceleration initial_layer_infill_speed initial_layer_jerk
initial_layer_speed initial_layer_travel_speed inner_wall_acceleration
inner_wall_jerk inner_wall_speed internal_bridge_speed internal_solid_infill_acceleration
internal_solid_infill_speed ironing_speed max_volumetric_extrusion_rate_slope
max_volumetric_extrusion_rate_slope_segment_length outer_wall_acceleration
outer_wall_jerk outer_wall_speed overhang_1_4_speed overhang_2_4_speed
overhang_3_4_speed overhang_4_4_speed slow_down_layers slowdown_for_curled_perimeters
small_perimeter_speed small_perimeter_threshold sparse_infill_acceleration
sparse_infill_speed support_interface_speed support_speed top_surface_acceleration
top_surface_jerk top_surface_speed travel_acceleration travel_jerk travel_speed
""".split())
_ADDED_DEFAULTS = {
    "filament_grouping_mode": "standard", "project_schema_version": "1",
    "printer_flow_support": ["standard"], "process_flow_support": ["standard"],
    "nozzle_volume_type": ["standard"] * 4,
    "filament_flow_support": ["standard"] * 5,
    "filament_volume_type": ["standard"] * 5,
    "filament_flow_step_size": ["1"] * 5,
}
PROCESS_COMBO = {"layer_height": "0.3", "sparse_infill_density": "30%", "enable_support": "1",
                 "support_type": "normal(auto)"}
QUALITY_ENUMS = {"ironing_type": "topmost", "seam_position": "random"}
MOVE_LAYER = {"layer_height": "0.24"}
# Feishu #254 层高组合: regular 0.20 mm with the initial layer raised to 0.25 mm.
LAYER_PAIR = {"layer_height": "0.2", "initial_layer_print_height": "0.25"}
# Feishu 常用工艺参数 supplement cases register their change scopes here at
# import time (harness.param_case_lib.make_verify); the whitelist below
# admits exactly these registered dicts plus the historical frozen scopes.
PARAM_CHANGE_SCOPES = set()


def _register_param_change_scope(values):
    if type(values) is dict and values:
        PARAM_CHANGE_SCOPES.add(tuple(sorted(values.items())))


PAIR_SETTINGS = tuple(expected_settings(scenario) for scenario in PAIR_CASES)


def require_gcode_settings(gcode, expected, error_code):
    lines = gcode.decode("utf-8").splitlines()
    lo, hi = lines.index("; CONFIG_BLOCK_START"), lines.index("; CONFIG_BLOCK_END")
    block = "\n".join(lines[lo + 1:hi]).encode()
    for key, wanted in expected.items():
        values = config_value_all(block, key)
        _require(values and all(value == wanted for value in values), error_code + ":" + key)


def inspect_preserved_settings(actual, expected, *, allowed_changes=None, cancelled=lambda: False):
    _require(type(actual) is dict and type(expected) is dict, "pilot_config_schema")
    changes = {} if allowed_changes is None else allowed_changes
    _require(type(changes) is dict and (not changes or changes in
             ({"wall_loops": "3"}, {"sparse_infill_density": "30%"}, {"top_shell_layers": "5"},
              {"bottom_shell_layers": "6"}, PROCESS_COMBO, QUALITY_ENUMS, MOVE_LAYER, LAYER_PAIR,
              *PAIR_SETTINGS)
             or tuple(sorted(changes.items())) in PARAM_CHANGE_SCOPES),
             "pilot_config_change_scope")
    if changes == {"wall_loops": "3"}:
        _require(expected.get("wall_loops") == "2" and actual.get("wall_loops") == "3",
                 "pilot_wall_loops_target")
    elif changes == {"sparse_infill_density": "30%"}:
        _require(expected.get("sparse_infill_density") == "15%"
                 and actual.get("sparse_infill_density") == "30%", "pilot_infill_target")
    elif changes == {"top_shell_layers": "5"}:
        _require(expected.get("top_shell_layers") == "3", "pilot_top_layers_baseline")
    elif changes == {"bottom_shell_layers": "6"}:
        _require(expected.get("bottom_shell_layers") == "3", "pilot_bottom_layers_baseline")
    _require(set(expected) <= set(actual), "pilot_config_missing")
    for key in set(actual)-set(expected):
        _check_cancel(cancelled)
        _require(key in _ADDED_DEFAULTS and actual[key] == _ADDED_DEFAULTS[key],
                 "pilot_config_unknown_addition")
    for key, before in expected.items():
        _check_cancel(cancelled)
        after = actual[key]
        if key in changes:
            _require(after == changes[key], "pilot_target_setting_mismatch")
            continue
        if after == before:
            continue
        if key in _VECTOR_MIGRATIONS and type(before) is str and after == [before]:
            continue
        if key in {"printer_settings_id", "print_settings_id"} and after == before+"(fixture.3mf)":
            continue
        if key == "filament_settings_id" and after == [v+"(fixture.3mf)" for v in before]:
            continue
        if key == "version" and before == "2.3.6" and after == "2.4.0":
            continue
        if key == "filament_ids" and before[0] == "GFSG99" and after == [""]+before[1:]:
            continue
        if key == "different_settings_to_system" and changes:
            if (type(before) is list and type(after) is list and len(before) == len(after)
                    and after[1:] == before[1:] and type(after[0]) is str):
                parts = after[0].split(";")
                if len(parts) == len(set(parts)) and set(parts) == set(before[0].split(";")) | set(changes):
                    continue
        raise _InvalidEvidence("pilot_unrelated_setting_changed:"+key)
