"""Independent saved-settings and export checks for the Feishu comparison lane."""
from collections import Counter
import hashlib
import math
import re

from .agent_verify import _require
from .pilot_common import _register_param_change_scope, inspect_preserved_settings
from .project_3mf import SETTINGS_MEMBER, _archive
from .script_verify import _check_cancel, _json

_BASELINES = {
    "265": ("0cccce4a3b3f40798bcab64c8a815680",
            "4e1b6d62ef07f56878b598edb20df27e862a24b133a4e38f45ea66c73f375ec4"),
    "276": ("e9aa6f88eca940b385bfe531703f644e",
            "ce990af357454e04a4ab6057e2126cd3183cf1ebb087d63525b7673464bbcf65"),
}
_COORD = re.compile(r"([XYEFPS])(-?(?:\d+(?:\.\d+)?|\.\d+))")
_ROLES = {"Outer wall", "Overhang wall", "Bridge", "Bottom surface", "Top surface"}


def comparison_baseline(row, harvest_root):
    run, digest = _BASELINES[row]
    data = (harvest_root / run / "exports" / "0001.gcode").read_bytes()
    _require(hashlib.sha256(data).hexdigest() == digest, "comparison_baseline_identity")
    return data


def _export(gcode, wanted, cancelled):
    """Read the fixed U1 relative-E export and retain modal state on deposits."""
    rows = gcode.decode("utf-8").splitlines()
    _require(rows.count("; CONFIG_BLOCK_START") == rows.count("; CONFIG_BLOCK_END") == 1,
             "comparison_export_config_block")
    start, end = rows.index("; CONFIG_BLOCK_START"), rows.index("; CONFIG_BLOCK_END")
    _require(start < end, "comparison_export_config_block")
    config = {}
    for line in rows[start + 1:end]:
        key, separator, value = line.removeprefix("; ").partition(" = ")
        if separator and key in wanted:
            _require(key not in config, "comparison_duplicate_export_key:" + key)
            config[key] = value
    for key, val in wanted.items():
        _require(config.get(key) == val, "comparison_export_key:" + key)

    moves, layers = [], []
    x = y = feed = fan = None
    tool, role = None, None
    relative_e, wiping = False, False
    for index, raw in enumerate(rows[:start]):
        if index % 1024 == 0:
            _check_cancel(cancelled)
        if raw.startswith(";Z:"):
            layers.append(float(raw[3:]))
        elif raw.startswith(";TYPE:"):
            role = raw[6:].strip()
        elif raw == ";WIPE_START":
            wiping = True
        elif raw == ";WIPE_END":
            wiping = False
        command = raw.partition(";")[0].strip().split()
        if not command:
            continue
        op = command[0]
        if op == "M83":
            relative_e = True
        elif op == "M82":
            relative_e = False
        elif re.fullmatch(r"T\d+", op):
            tool = int(op[1:])
        elif op in {"M106", "M107", "G0", "G1", "G2", "G3"}:
            args = {key: float(value) for key, value in _COORD.findall(" ".join(command[1:]))}
            if op in {"M106", "M107"}:
                if args.get("P", 0) in (0, 1):
                    fan = args.get("S", 255) if op == "M106" else 0
                continue
            feed = args.get("F", feed)
            nx, ny = args.get("X", x), args.get("Y", y)
            if (layers and role in _ROLES and not wiping and args.get("E", 0) > 0
                    and None not in (x, y, nx, ny) and (nx, ny) != (x, y)):
                _require(relative_e and op in {"G0", "G1"} and feed and tool == 0,
                         "comparison_unexpected_deposition_format")
                moves.append(((layers[-1], role, x, y, nx, ny), feed / 60, fan, args["E"]))
            x, y = nx, ny
    _require(layers and moves, "comparison_export_deposition_missing")
    return layers, moves


def _fan_effect(before, after):
    ordinary = {"Bottom surface", "Top surface"}
    overhang = {"Overhang wall", "Bridge"}
    base_moves = {path: (speed, fan) for path, speed, fan, _ in before}
    matched = [(path[1], speed, fan, *base_moves[path])
               for path, speed, fan, _ in after if path in base_moves]
    slowed = sum(speed < old - 0.01 for role, speed, _, old, _ in matched
                 if role in {"Outer wall", "Overhang wall"})
    _require(slowed > 0, "comparison_curled_slowdown_missing")
    surface = [(speed, fan, old_speed, old_fan)
               for role, speed, fan, old_speed, old_fan in matched if role in ordinary]
    _require(surface, "comparison_ordinary_surface_missing")
    surface_feed_changes = sum(abs(speed - old) >= 0.01 for speed, _, old, _ in surface)
    surface_fan_changes = sum(fan != prior for _, fan, _, prior in surface)
    fan_hits = sum(abs((fan if fan is not None else -1) - 204) <= 1 and fan != prior
                   for role, _, fan, _, prior in matched if role in overhang)
    return {"matched_wall_slowdowns": slowed, "ordinary_surface_matches": len(surface),
            "ordinary_surface_feed_changes": surface_feed_changes,
            "ordinary_surface_fan_changes": surface_fan_changes, "overhang_80pct_matches": fan_hits,
            "fan_effect": "observed" if fan_hits else "not_observed",
            "overhang_percentage_threshold": "not_observable_in_export"}


def _flow_effect(before, after, first_z, diameter):
    old = [(path, feed) for path, feed, _, _ in before if path[0] != first_z and path[1] == "Outer wall"]
    new = [(path, feed, e) for path, feed, _, e in after if path[0] != first_z and path[1] == "Outer wall"]
    _require(old and new and Counter(path for path, _ in old) == Counter(path for path, _, _ in new),
             "comparison_outer_wall_paths_changed")
    flows = []
    for (_, _, x0, y0, x1, y1), speed, extrusion in new:
        dx, dy = x1 - x0, y1 - y0
        distance = math.hypot(dx, dy)
        _require(speed * abs(dx) / distance <= 500.01, "comparison_outer_wall_x_limit")
        # Emitted E is filament length per move, not nominal layer height times width.
        if distance >= 1:
            flows.append(speed * extrusion * math.pi * (diameter / 2) ** 2 / distance)
    _require(flows and 14.5 <= max(flows) <= 15.5, "comparison_outer_wall_volumetric_cap")
    peak = max(speed for _, speed, _ in new)
    prior_peak = max(speed for _, speed in old)
    _require(prior_peak < peak < 700, "comparison_outer_wall_feed_response")
    return {"baseline_outer_wall_peak_mm_s": round(prior_peak, 3),
            "outer_wall_peak_mm_s": round(peak, 3),
            "outer_wall_peak_mm3_s": round(max(flows), 3),
            "near_feishu_178_mm_s": abs(peak - 178) <= 5,
            "x_limit_effect": "not_exercised_by_flow_limited_outer_walls"}


def _scene(files):
    """Normalize only the observed serializer-only fields on these fixtures."""
    normalized = {}
    for name, data in files.items():
        if name.endswith(".model"):
            ignored = r'<metadata name="Application">(?:BambuStudio-2[.]3[.]6|Snapmaker_Orca-2[.]4[.]0)</metadata>'
        elif name == "Metadata/model_settings.config":
            ignored = r'<metadata key="(?:source_file|identify_id)" value="[^"]*"/>'
        else:
            continue
        normalized[name] = tuple(line for raw in data.decode("utf-8").splitlines()
                                 if (line := raw.strip()) and not re.fullmatch(ignored, line))
    return normalized


def make_comparison_verify(row, process_values, slot_values, machine_values=None):
    machine_values = machine_values or {}
    changes = {**process_values, **{key: (0, value) for key, value in slot_values.items()},
               **{key: (0, value) for key, value in machine_values.items()}}
    _register_param_change_scope(changes)

    def verify(project, fixture, gcode, *, baseline_gcode=None, cancelled=lambda: False):
        project_files = _archive(project, cancelled)
        fixture_files = _archive(fixture, cancelled)
        actual = _json(project_files[SETTINGS_MEMBER])
        original = _json(fixture_files[SETTINGS_MEMBER])
        manifest = {0: set(process_values), 1: set(slot_values), 6: set(machine_values)}
        inspect_preserved_settings(actual, original, allowed_changes=changes,
                                   manifest_scopes=manifest, cancelled=cancelled)
        _require(_scene(project_files) == _scene(fixture_files), "comparison_project_scene_changed")

        def export_values(settings):
            return {key: ",".join(settings[key]) if isinstance(settings[key], list)
                    else settings[key] for key in changes}

        layers, moves = _export(gcode, export_values(actual), cancelled)
        result = {"row": row, "target_filament_slot": 1, "target_values": {
            **process_values, **slot_values, **machine_values}, "other_settings_preserved": True,
            "scene_preserved": True,
            "layer_count": len(layers), "gcode_sha256": hashlib.sha256(gcode).hexdigest(),
            "pair_status": "baseline_required"}
        if baseline_gcode is None:
            return result
        run, digest = _BASELINES[row]
        _require(hashlib.sha256(baseline_gcode).hexdigest() == digest, "comparison_baseline_identity")
        baseline_layers, baseline_moves = _export(baseline_gcode, export_values(original), cancelled)
        _require(layers == baseline_layers, "comparison_layer_grid_changed")
        if row == "265":
            effect = _fan_effect(baseline_moves, moves)
        else:
            effect = _flow_effect(baseline_moves, moves, layers[0], float(actual["filament_diameter"][0]))
        result.update(effect, baseline_run=run, baseline_gcode_sha256=digest, pair_status="checked")
        return result

    return verify


def comparison_business_status(detail):
    """Report complete Feishu acceptance separately from completed comparison."""
    if detail.get("pair_status") != "checked":
        return {"comparison_checked": False, "business_status": "UNVERIFIED",
                "unmet_expectations": ["comparison_baseline"]}
    if detail["row"] == "265":
        expectations = {
            "overhang_80pct": detail.get("fan_effect") == "observed",
            "overhang_10pct_transition": detail.get("overhang_percentage_threshold") == "observed",
            "curled_wall_slowdown": detail.get("matched_wall_slowdowns", 0) > 0,
            "ordinary_surface_feed": detail.get("ordinary_surface_feed_changes") == 0,
            "ordinary_surface_fan": detail.get("ordinary_surface_fan_changes") == 0,
        }
    else:
        expectations = {
            "outer_wall_near_178_mm_s": detail.get("near_feishu_178_mm_s") is True,
            "machine_x_limit_intervention": detail.get("x_limit_effect") == "observed",
        }
    unmet = [name for name, proven in expectations.items() if not proven]
    return {"comparison_checked": True, "business_status": "SHADOW" if unmet else "PASS",
            "unmet_expectations": unmet}
