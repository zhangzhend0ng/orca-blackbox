"""Where Feishu #262's "object flow stays the same" holds and where it cannot.

#262 expects the top surface to extrude about 10% more, the bottom surface
about 10% less, and the object's overall flow to stay the same. The three
cannot all describe the deposited filament unless the baseline top and bottom
happen to extrude the same amount. With every other feature unchanged, the
object's extrusion has to move by

    (top_ratio - 1) * baseline_top + (bottom_ratio - 1) * baseline_bottom.

This tool measures both sides of that identity on two G-code files of one
plate (baseline, target) and on an optional reversed control:

    python tools/check_surface_flow_balance.py --baseline a.gcode --target b.gcode [--control c.gcode]

Counted is E > 0 on a move that also carries X or Y, under the `;TYPE:` block
in force, between `; printing object` and `; stop printing object`. Retractions,
primes and wipes are not netted out; they are reported separately as `side_e`.
The three flow ratios are read from each file's emitted CONFIG block. Exit
status 0 means the identity held within the E write step for every pair.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import struct

TOP, BOTTOM = "Top surface", "Bottom surface"
SURFACES = {"top": TOP, "bottom": BOTTOM}
RATIO_KEYS = {"top": "top_solid_infill_flow_ratio", "bottom": "bottom_solid_infill_flow_ratio",
              "object": "print_flow_ratio"}
OBJECT_MARKER = re.compile(r"; (printing|stop printing) object (.*?) id:(\d+) copy (\d+)")
CONFIG_BLOCK = re.compile(r"^; CONFIG_BLOCK_START\r?\n(.*?)^; CONFIG_BLOCK_END\r?$", re.M | re.S)
CONFIG_ENTRY = re.compile(r"^; (\w+) = ([^\r\n]*)", re.M)
PACK = struct.Struct("<7d")   # x0 y0 z0 x1 y1 z1 e of one segment
AMOUNT = struct.Struct("<d")


def flow_ratios(text: str) -> dict[str, float]:
    """The three flow ratios as the file's single CONFIG block emits them."""
    blocks = CONFIG_BLOCK.findall(text)
    if len(blocks) != 1:
        raise ValueError("expected one emitted configuration block")
    entries = defaultdict(list)
    for key, value in CONFIG_ENTRY.findall(blocks[0]):
        entries[key].append(value)
    ratios = {}
    for name, key in RATIO_KEYS.items():
        values = entries[key]
        if len(values) != 1:
            raise ValueError(f"{key}: expected one emitted value, found {len(values)}")
        try:
            ratio = float(values[0])
        except ValueError as exc:
            raise ValueError(f"{key}: not a number: {values[0]!r}") from exc
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError(f"{key}: expected a positive ratio, found {values[0]!r}")
        ratios[name] = ratio
    return ratios


def _step(word: str) -> float:
    """Smallest step an E word can express: `.00294` -> 0.00001."""
    return 10.0 ** -len(word.partition(".")[2])


def read_plate(path: Path) -> dict:
    """Positive XY extrusion per feature, inside and outside labelled objects."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    point = dict.fromkeys("XYZE")
    absolute = relative_e = None
    feature, active = "", None
    features, outside, objects = {}, {}, defaultdict(float)
    surface = {name: [] for name in SURFACES.values()}
    step, side_e = 1.0, 0.0
    for raw in text.splitlines():
        if raw.startswith(";TYPE:"):
            feature = raw[6:].strip()
            continue
        marker = OBJECT_MARKER.fullmatch(raw)
        if marker:
            label = marker[2], marker[3], marker[4]
            if marker[1] == "printing":
                if active is not None:
                    raise ValueError("nested object")
                active = label
            else:
                if active != label:
                    raise ValueError("unpaired object end")
                active = None
            continue
        words = raw.partition(";")[0].split()
        if words and words[0][0] == "N" and words[0][1:].isdigit():
            words = words[1:]
        if not words:
            continue
        op = words[0]
        if op[0] == "G" and op[1:].isdigit():
            op = "G" + str(int(op[1:]))
        if op in ("M221", "M200"):
            raise ValueError("firmware extrusion scaling is outside this tool")
        if op in ("G90", "G91"):
            absolute = op == "G90"
            continue
        if op in ("M82", "M83"):
            relative_e = op == "M83"
            continue
        if op not in ("G0", "G1", "G2", "G3", "G92"):
            continue
        try:
            fields = {word[0]: word[1:] for word in words[1:] if word[0] in "XYZE"}
            values = {axis: float(word) for axis, word in fields.items()}
        except ValueError as exc:
            raise ValueError(f"malformed coordinate in {raw!r}") from exc
        if op == "G92":
            point.update(values)
            continue
        previous = point.copy()
        for axis, value in values.items():
            relative = relative_e if axis == "E" else not absolute
            point[axis] = (point[axis] or 0) + value if relative else value
        amount = None
        if "E" in values:
            # The power-on E position is 0, as on the firmware.
            amount = values["E"] if relative_e else (point["E"] or 0) - (previous["E"] or 0)
        if amount is None or not ({"X", "Y"} & values.keys()):
            if active is not None and amount is not None and relative_e is not None:
                side_e += amount  # prime or retraction without XY
            continue
        if amount <= 0:
            if active is not None and relative_e is not None:
                side_e += amount  # wipe taken while retracting
            continue
        if absolute is None or relative_e is None:
            raise ValueError("extruding move before G90/M82/M83 declared the modes")
        name = feature or "Custom"
        row = {"positive": 0.0, "segments": 0, "digest": hashlib.sha256()}
        if active is None:
            # Purge and skirt lines start wherever the start G-code left the head.
            row = outside.setdefault(name, row)
            row["positive"] += amount
            row["segments"] += 1
            row["digest"].update(AMOUNT.pack(amount))
            continue
        if any(previous[axis] is None for axis in "XYZ") or any(point[axis] is None for axis in "XYZ"):
            raise ValueError("unknown position on an extruding move inside an object")
        if op in ("G2", "G3"):
            raise ValueError("extruding arc is outside this tool")
        segment = tuple(previous[axis] for axis in "XYZ") + tuple(point[axis] for axis in "XYZ") + (amount,)
        row = features.setdefault(name, row)
        row["positive"] += amount
        row["segments"] += 1
        row["digest"].update(PACK.pack(*segment))
        objects[active] += amount
        if name in surface:
            surface[name].append(segment)
            step = min(step, _step(fields["E"]))
    if active is not None:
        raise ValueError("object marker never closed")
    for table in (features, outside):
        for row in table.values():
            row["digest"] = row["digest"].hexdigest()
    return {"path": str(path), "ratios": flow_ratios(text), "layers": text.count("\n;LAYER_CHANGE"),
            "features": features, "outside": outside, "surface": surface, "step": step, "side_e": side_e,
            "objects": [{"name": key[0], "id": key[1], "copy": key[2], "positive": total}
                        for key, total in objects.items()]}


def _sum(values) -> float:
    return math.fsum(values)


def _surface(baseline: dict, target: dict, name: str, scale: float) -> dict:
    """One surface: totals, whether the paths survived, and the per-segment residuals."""
    first, last = baseline["surface"][name], target["surface"][name]
    same = len(first) == len(last) and all(x[:6] == y[:6] for x, y in zip(first, last))
    deviations = [y[6] - x[6] * scale for x, y in zip(first, last)]
    return {"baseline": _sum(x[6] for x in first), "target": _sum(y[6] for y in last),
            "segments": [len(first), len(last)], "paths_identical": same,
            "deviation_sum": _sum(deviations) if same else None,
            "max_abs_deviation": max(map(abs, deviations), default=0.0) if same else None}


def _other(baseline: dict, target: dict, name: str) -> dict:
    first, last = baseline["features"].get(name), target["features"].get(name)
    both = first is not None and last is not None
    return {"baseline": first["positive"] if first else None, "target": last["positive"] if last else None,
            "segments": [first["segments"] if first else 0, last["segments"] if last else 0],
            "identical": bool(both and first["digest"] == last["digest"])}


def compare(baseline: dict, target: dict) -> dict:
    """Residual of the identity on one baseline/target pair of `read_plate` results."""
    emitted = {name: [baseline["ratios"][name], target["ratios"][name]] for name in RATIO_KEYS}
    scale = {name: emitted[name][1] / emitted[name][0] for name in SURFACES}
    surfaces = {name: _surface(baseline, target, feature, scale[name]) for name, feature in SURFACES.items()}
    names = sorted((set(baseline["features"]) | set(target["features"])) - set(SURFACES.values()))
    others = {name: _other(baseline, target, name) for name in names}
    object_total = [_sum(row["positive"] for row in plate["features"].values()) for plate in (baseline, target)]
    outside_total = [_sum(row["positive"] for row in plate["outside"].values()) for plate in (baseline, target)]
    measured = object_total[1] - object_total[0]
    predicted = sum((scale[name] - 1) * surfaces[name]["baseline"] for name in SURFACES)
    step = min(baseline["step"], target["step"])
    limit = {name: 0.5 * step * (1 + scale[name]) for name in SURFACES}
    # Each written E is the true value rounded to the write step, so one segment
    # can be off by at most (1 + scale) half steps and the sum by that over all.
    bound = sum(sum(surfaces[name]["segments"]) * limit[name] for name in SURFACES)
    quantized = all(surfaces[name]["paths_identical"]
                    and surfaces[name]["max_abs_deviation"] <= limit[name] * (1 + 1e-9) for name in SURFACES)
    paths = all(surfaces[name]["paths_identical"] for name in SURFACES)
    unchanged = bool(others) and all(row["identical"] for row in others.values())
    top_base, bottom_base = (surfaces[name]["baseline"] for name in SURFACES)
    return {
        "emitted_ratios": emitted, "scale": scale,
        "top": surfaces["top"], "bottom": surfaces["bottom"], "other_features": others,
        "object_positive": {"baseline": object_total[0], "target": object_total[1]},
        "outside_positive": {"baseline": outside_total[0], "target": outside_total[1]},
        "side_e": [baseline["side_e"], target["side_e"]], "layers": [baseline["layers"], target["layers"]],
        "measured_delta": measured, "predicted_delta": predicted, "residual": measured - predicted,
        "formula": f"({scale['top'] - 1:.6g}) * {top_base:.6f} + ({scale['bottom'] - 1:.6g}) * {bottom_base:.6f}",
        "e_write_step": step, "segment_limit": limit, "residual_bound": bound,
        "checks": {
            "top_and_bottom_paths_identical": paths,
            "other_features_identical": unchanged,
            "top_and_bottom_within_write_step": quantized,
            "print_flow_ratio_unchanged": emitted["object"][0] == emitted["object"][1],
            "balance_identity_holds": paths and unchanged and quantized and abs(measured - predicted) <= bound,
            # the total counts as unchanged only within what the E write step can express
            "object_positive_unchanged": abs(measured) <= bound,
        },
    }


def _line(label: str, first: float, last: float, ratio: float | None = None) -> str:
    factor = f"{ratio:.6f}" if ratio is not None else ""
    return f"  {label:<22}{first:>15.6f}{last:>15.6f} {factor:>10}"


def _show(title: str, result: dict) -> None:
    ratios = result["emitted_ratios"]
    print(f"== {title}: top {ratios['top'][0]:g} -> {ratios['top'][1]:g}, "
          f"bottom {ratios['bottom'][0]:g} -> {ratios['bottom'][1]:g}, "
          f"print_flow_ratio {ratios['object'][0]:g} -> {ratios['object'][1]:g}; "
          f"layers {result['layers'][0]} -> {result['layers'][1]}")
    for name, key in (("Top surface", "top"), ("Bottom surface", "bottom")):
        row = result[key]
        ratio = row["target"] / row["baseline"] if row["baseline"] else float("nan")
        print(_line(name, row["baseline"], row["target"], ratio)
              + f"  segments {row['segments'][0]} -> {row['segments'][1]}, "
                f"max |segment residual| {row['max_abs_deviation']}")
    other = result["other_features"]
    first = _sum(row["baseline"] or 0 for row in other.values())
    last = _sum(row["target"] or 0 for row in other.values())
    print(_line(f"other ({len(other)} features)", first, last, last / first if first else float("nan"))
          + f"  segment streams {'identical' if result['checks']['other_features_identical'] else 'DIFFER'}")
    obj = result["object_positive"]
    print(_line("object positive E", obj["baseline"], obj["target"],
                obj["target"] / obj["baseline"] if obj["baseline"] else float("nan"))
          + f"  ({(obj['target'] / obj['baseline'] - 1) * 100:+.5f} %)")
    outside = result["outside_positive"]
    print(_line("outside objects", outside["baseline"], outside["target"]))
    print(_line("side E (retract/prime)", *result["side_e"]))
    print(f"  measured delta {result['measured_delta']:+.6f}   predicted {result['predicted_delta']:+.6f}"
          f"   residual {result['residual']:+.6f}")
    print(f"  predicted = {result['formula']}; E write step {result['e_write_step']:g}; "
          f"|residual| bound {result['residual_bound']:.6f}")
    for name, value in result["checks"].items():
        print(f"  {'PASS' if value else 'FAIL'} {name}")


def _summary(plate: dict) -> dict:
    """`read_plate` output without the per-segment lists."""
    return {key: value for key, value in plate.items() if key != "surface"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--control", type=Path, help="the reversed pair (e.g. 0.9 / 1.1) of the same baseline")
    parser.add_argument("--json", type=Path, help="also write the full report to this file")
    args = parser.parse_args()
    baseline = read_plate(args.baseline)
    report = {"baseline": _summary(baseline)}
    for title, path in (("target", args.target), ("control", args.control)):
        if path is not None:
            report[title] = compare(baseline, read_plate(path))
            _show(title, report[title])
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    held = [report[title]["checks"]["balance_identity_holds"] for title in ("target", "control") if title in report]
    return 0 if all(held) else 1


if __name__ == "__main__":
    raise SystemExit(main())
