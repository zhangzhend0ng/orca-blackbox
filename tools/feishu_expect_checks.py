"""Observable G-code checks for four Feishu rows on their designated fixtures."""
from pathlib import Path
import hashlib
import json

from gcode_facts import gcode_facts


def measured_check(number, baseline, run):
    if number == 258:
        before, after = baseline["arcs"]["extruding"], run["arcs"]["extruding"]
        return before == 0 and after > 0, f"extruding arcs {before} -> {after}"
    if number == 262:
        changes = {}
        for name in ("Top surface", "Bottom surface"):
            before = baseline["features"].get(name, {}).get("e_per_mm")
            after = run["features"].get(name, {}).get("e_per_mm")
            if not before or after is None:
                return None, f"missing {name} extrusion per mm"
            changes[name] = after / before
        top, bottom = changes.values()
        return (1.09 <= top <= 1.11 and 0.89 <= bottom <= 0.91,
                f"E/mm ratio top {top:.4f}, bottom {bottom:.4f} (tolerance 0.01)")
    if number == 273:
        # Other-layer XY travels include slower machine moves. This checks
        # the most frequent feed only, with no claim about every travel.
        before = baseline["travel_feeds"]["other"]
        after = run["travel_feeds"]["other"]
        if not before or not after:
            return None, "missing non-first-layer travel moves"
        initial, final = float(before[0][0]), float(after[0][0])
        return initial == 30000 and final == 18000, f"most frequent travel feed {initial:g} -> {final:g}"
    if number == 277:
        counts = []
        for facts in (baseline, run):
            counts.append(tuple(facts["features"].get(name, {}).get("moves", 0)
                                for name in ("Support", "Support interface")))
        return counts[0] == (0, 0) and min(counts[1]) > 0, f"support and interface moves {counts[0]} -> {counts[1]}"
    raise ValueError(f"unsupported Feishu row {number}")


def read_export(directory, fixture_sha):
    if not directory:
        raise ValueError("run missing")
    root = Path(directory)
    def record(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))
    result, proof = record("result.json"), record("proof.json")
    if result.get("release_verdict") != "SHADOW" or proof.get("run_id") != root.name:
        raise ValueError("missing SHADOW or mismatched proof identity")
    if hashlib.sha256((root / "input/fixture.3mf").read_bytes()).hexdigest() != fixture_sha:
        raise ValueError("wrong input fixture")
    exports = list((root / "exports").glob("*.gcode"))
    if len(exports) != 1 or hashlib.sha256(exports[0].read_bytes()).hexdigest() != proof.get("gcode_sha256"):
        raise ValueError("missing, ambiguous or unverified export")
    return gcode_facts(exports[0]), proof["sut_sha256"]


def compare(number, baseline, run, fixture_sha):
    try:
        base_facts, base_build = read_export(baseline, fixture_sha)
        run_facts, run_build = read_export(run, fixture_sha)
        if not base_build or base_build != run_build:
            return None, "baseline and case build identities differ"
        return measured_check(number, base_facts, run_facts)
    except (KeyError, ValueError, OSError, TypeError) as exc:
        return None, str(exc)
