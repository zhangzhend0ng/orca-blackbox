"""Compare object extrusion geometry and flow for Feishu #262 on its single Benchy."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

FLOW_KEYS = ("top_solid_infill_flow_ratio", "bottom_solid_infill_flow_ratio", "print_flow_ratio")
EXPECTED = {"Top surface": 1.1, "Bottom surface": 0.9}


def _config_entries(text):
    blocks = re.findall(r"^; CONFIG_BLOCK_START\r?\n(.*?)^; CONFIG_BLOCK_END\r?$", text, re.M | re.S)
    if len(blocks) != 1:
        raise ValueError("expected one emitted configuration block")
    entries = defaultdict(list)
    for key, value in re.findall(r"^; (\w+) = ([^\r\n]*)", blocks[0], re.M):
        entries[key].append(value)
    if any(len(entries.get(key, [])) != 1 for key in FLOW_KEYS):
        raise ValueError("expected one emitted value for each flow setting")
    return dict(entries)


def _config_delta(before, after):
    # Orca repeats some keys (including wipe_tower_x/y) in a single block. Compare
    # every occurrence so an unrelated change cannot hide behind a later value.
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    target_keys = set(FLOW_KEYS[:2])
    dirty_key = "different_settings_to_system"
    unexpected = [key for key in changed if key not in target_keys and key != dirty_key]
    if dirty_key in changed:
        def other_dirty_keys(entries):
            return [[token for token in value.split(";") if token not in target_keys]
                    for value in entries.get(dirty_key, [])]

        if other_dirty_keys(before) != other_dirty_keys(after):
            unexpected.append(dirty_key)
    return {"pass": not unexpected, "key_counts": [len(before), len(after)],
            "changed_keys": changed, "unexpected_changes": sorted(unexpected)}


def _read(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    config = _config_entries(text)
    point = dict.fromkeys("XYZE")
    absolute = relative_e = active = None
    feature = ""
    groups = defaultdict(list)
    objects = set()
    completed = 0
    for line in text.splitlines():
        if line.startswith(";TYPE:"):
            feature = line[6:].strip()
        marker = re.fullmatch(r"; (printing|stop printing) object (.*?) id:(\d+) copy (\d+)", line)
        if marker:
            label = marker.groups()[1:]
            if marker[1] == "printing":
                if active is not None:
                    raise ValueError("nested object")
                active = label
                objects.add(label)
            else:
                if active != label:
                    raise ValueError("unpaired object end")
                active = None
                completed += 1
        cmd = line.partition(";")[0].split()
        if not cmd:
            continue
        op = cmd[0]
        if op in ("M221", "M200"):
            raise ValueError("firmware extrusion scaling is outside this verifier")
        if op in ("G90", "G91"):
            absolute = op == "G90"
        elif op in ("M82", "M83"):
            relative_e = op == "M83"
        elif op in ("G0", "G1", "G2", "G3", "G92"):
            fields = {s[0]: float(s[1:]) for s in cmd[1:] if s[0] in "XYZE"}
            if op == "G92":
                point.update(fields)
                continue
            prev = point.copy()
            for axis, amount in fields.items():
                relative = relative_e if axis == "E" else not absolute
                point[axis] = (point[axis] or 0) + amount if relative else amount
            if not active or "E" not in fields or not ({"X", "Y"} & fields.keys()):
                continue
            if absolute is None or relative_e is None:
                raise ValueError("unknown coordinate mode")
            amount = fields["E"] if relative_e else point["E"] - prev["E"]
            if amount <= 0:
                continue
            if op not in ("G0", "G1") or None in [p[k] for p in (prev, point) for k in "XYZ"]:
                raise ValueError("unsupported extruding arc or unknown position")
            endpoints = tuple(tuple(p[k] for k in "XYZ") for p in (prev, point))
            if endpoints[0][:2] != endpoints[1][:2]:
                groups[feature].append((endpoints, amount))
    if active is not None or not completed or len(objects) != 1 or "benchy" not in next(iter(objects))[0].lower():
        raise ValueError("expected one complete labelled Benchy print object")
    return config, groups


def verify(baseline, target):
    baseline_entries, first = _read(baseline)
    target_entries, last = _read(target)
    effective_config = _config_delta(baseline_entries, target_entries)
    a = {key: values[-1] for key, values in baseline_entries.items()}
    b = {key: values[-1] for key, values in target_entries.items()}
    cfg = {k: [a.get(k), b.get(k)] for k in FLOW_KEYS}
    settings = all(math.isclose(float(a[k]), 1) and math.isclose(float(b[k]), want)
                   for k, want in zip(FLOW_KEYS, (1.1, 0.9, 1.0)))
    def expected_profile(config):
        return (config.get("printer_model") == "Snapmaker U1"
                and set(config.get("filament_type", "").split(";")) == {"PLA"}
                and set(config.get("nozzle_diameter", "").split(",")) == {"0.4"}
                and float(config["layer_height"]) == 0.20
                and config.get("print_settings_id", "").startswith("0.20mm Standard @Snapmaker U1 (0.4 nozzle)"))

    profiles_match = (expected_profile(a) and expected_profile(b) and bool(a.get("filament_flow_ratio"))
                      and a["filament_flow_ratio"] == b.get("filament_flow_ratio"))
    report = {}
    for name in sorted(set(first) | set(last)):
        left, right = sorted(first[name]), sorted(last[name])
        same = len(left) == len(right) and all(x[0] == y[0] for x, y in zip(left, right))
        sums = [sum(distance for _, distance in arm) for arm in (left, right)]
        ratio = sums[1] / sums[0] if sums[0] else None
        wanted = EXPECTED.get(name, 1)
        # Absolute allowance for the quantization of short G1 E values.
        mismatches = sum(not math.isclose(y[1], x[1]*wanted, rel_tol=0.005, abs_tol=0.000025)
                         for x, y in zip(left, right)) if same else None
        report[name] = {"segments": [len(left), len(right)], "paths_identical": same,
                        "extrusion_mm": sums,
                        "extrusion_ratio": ratio, "segment_e_mismatches": mismatches}
    shape = report.get("Outer wall", {}).get("paths_identical", False)
    sufficient = all(k in first and k in last for k in (*EXPECTED, "Outer wall", "Inner wall"))
    extrusion_matches = all(
        row["paths_identical"] and row["segment_e_mismatches"] == 0
        and math.isclose(row["extrusion_ratio"], EXPECTED.get(name, 1), abs_tol=0.005)
        for name, row in report.items()
    )
    ok = effective_config["pass"] and settings and profiles_match and sufficient and shape and extrusion_matches
    totals = [sum(row["extrusion_mm"][i] for row in report.values()) for i in range(2)]
    return {"pass": ok, "flow_config": cfg, "config_matches": settings, "profile_matches": profiles_match,
            "effective_config": effective_config, "outer_shell_paths_identical": shape,
            "all_labelled_features_extrusion_mm": totals, "all_labelled_features_ratio": totals[1] / totals[0],
            "feature_extrusion": report, "input_sha256": [hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                                          for p in (baseline, target)]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.baseline, args.target)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
