"""Independent re-check of the ten 'fa'-line SHADOW parameter runs.

For each run: open the saved project <run>/artifacts/projects/0001.3mf, read
Metadata/project_settings.config and compare every VALUES key of the matching
harness/pilot_param_*.py module against the saved value. The case modules are
parsed with ast and never imported, so no repo code runs and nothing is
written to the worktree. This script writes nothing anywhere.

    C:\\coil\\orca-blackbox-glm\\.venv\\Scripts\\python.exe -B verify_fa_shadows.py [-v]

Exit code: 0 all keys match, 1 at least one mismatch, 2 at least one run unreadable.
"""
import ast
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

WORKTREE = Path(r"C:\coil\orca-blackbox-glm")
PROJECT = "artifacts/projects/0001.3mf"
SETTINGS_MEMBER = "Metadata/project_settings.config"
REPORT_KEYS = ("layer_height", "spiral_mode", "enable_support")

# run id -> harness case module, as handed over for this re-check
RUNS = (
    ("0c8f604e6c38432f9bbf48055ef561f9", "pilot_param_279_support_filament"),
    ("b9d0efa53cba4c74980aa52971cede8e", "pilot_param_284_filament_features"),
    ("83cce0335001478882752a5f06cf9189", "pilot_param_281_support_interface"),
    ("51380cfe684944659ab278bf93d24900", "pilot_param_280_support_ironing"),
    ("d9df6fdbb24745f092ab78b78d52fd54", "pilot_param_287_material_advanced"),
    ("6b8fa2d9288f4d96a136a17db0c049ee", "pilot_param_295_fuzzy"),
    ("2bacb63495cc43f29ff452d6148b0634", "pilot_param_283_prime_tower"),
    ("e946ad140e2e45f397951d8f5ae9a9fe", "pilot_param_282_tree_support"),
    ("f0175fa74c8943dd9550b53d6a5fed89", "pilot_param_286_flush_options"),
    ("0eb5a4177f0b4effa37f062c132201f9", "pilot_param_285_ooze_prevention"),
)

_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")


def as_number(text):
    """Decimal for a plain numeric string, else None."""
    if isinstance(text, str) and _NUMBER.match(text.strip()):
        try:
            return Decimal(text.strip())
        except InvalidOperation:
            return None
    return None


def compare(expected, actual):
    """'exact', 'numeric' (equal as Decimal, e.g. '0.20' vs '0.2') or None."""
    if expected == actual:
        return "exact"
    expected_num, actual_num = as_number(expected), as_number(actual)
    if expected_num is not None and actual_num is not None and expected_num == actual_num:
        return "numeric"
    return None


def load_case(source):
    """VALUES dict of a case module, read as source text (no import)."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    values = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) and node.value else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "VALUES":
                values[node.lineno] = ast.literal_eval(node.value)
    if len(values) != 1 or not isinstance(next(iter(values.values())), dict):
        raise ValueError(f"expected exactly one module-level VALUES dict, "
                         f"found {sorted(values)}")
    value = next(iter(values.values()))
    bad = [k for k, v in value.items() if not isinstance(k, str) or not isinstance(v, str)]
    if bad:
        raise ValueError(f"VALUES entries that are not str->str: {bad}")
    return value


def scalar(value):
    """Saved value as one string plus a note; (None, reason) when not a scalar."""
    if isinstance(value, str):
        return value, ""
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], str):
            return value[0], ""
        if value and all(isinstance(v, str) for v in value) and len(set(value)) == 1:
            return value[0], f"uniform {len(value)}-element array"
        return None, "empty array" if not value else f"{len(value)}-element array {value!r}"
    return None, f"unexpected type {type(value).__name__} {value!r}"


def load_settings(raw):
    """Parse project_settings.config, keeping the keys JSON would silently collapse."""
    duplicates = []

    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                duplicates.append(key)
            out[key] = value
        return out

    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=hook), duplicates


def read_project(path, keys):
    """Saved settings of one project plus anything odd about the archive."""
    with zipfile.ZipFile(path) as archive:
        count = archive.namelist().count(SETTINGS_MEMBER)
        if count != 1:
            raise ValueError(f"{count} archive members named {SETTINGS_MEMBER}")
        settings, duplicates = load_settings(archive.read(SETTINGS_MEMBER))
        overrides = []
        # object / part overrides would supersede the global value when slicing
        for name in archive.namelist():
            if name != "Metadata/model_settings.config" and not name.startswith("3D/Objects/"):
                continue
            for elem in ET.fromstring(archive.read(name)).iter("metadata"):
                if elem.get("key") in keys:
                    overrides.append(f"{name}: {elem.get('key')}={elem.get('value')!r}")
    return settings, duplicates, overrides


def manifest_identity(run_dir, run_id, module):
    """'' when the run's own manifest names this run id and case, else why not."""
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return f"manifest.json unreadable ({type(exc).__name__}: {exc})"
    case_id = "param_" + module[len("pilot_param_"):]
    if (manifest.get("run_id"), manifest.get("case_id")) != (run_id, case_id):
        return f"manifest names run/case {manifest.get('run_id')}/{manifest.get('case_id')}"
    return ""


def check_run(run_id, module):
    source = WORKTREE / "harness" / f"{module}.py"
    run_dir = WORKTREE / "artifacts" / "v3" / run_id
    values = load_case(source)
    settings, duplicates, overrides = read_project(run_dir / PROJECT, set(values))
    if not isinstance(settings, dict):
        raise ValueError(f"{SETTINGS_MEMBER} is not a JSON object")
    keys = []
    for key, expected in values.items():
        actual, note = scalar(settings.get(key, None)) if key in settings else (None, "missing key")
        keys.append((key, expected, actual, compare(expected, actual) is not None, note))
    reported = {key: scalar(settings[key])[0] if key in settings else None for key in REPORT_KEYS}
    notes = [f"key defined twice in project_settings.config: {key}" for key in duplicates if key in values]
    notes += [f"object/part override: {hit}" for hit in overrides]
    identity = manifest_identity(run_dir, run_id, module)
    if identity:
        notes.append(f"run/case identity not confirmed: {identity}")
    return keys, reported, notes


def main(argv):
    verbose = "-v" in argv or "--verbose" in argv
    rows, reported_rows, details, notes, unreadable = [], [], [], [], []
    total_keys = total_bad = 0
    for run_id, module in RUNS:
        try:
            keys, reported, run_notes = check_run(run_id, module)
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
            unreadable.append(f"UNREADABLE {run_id[:8]} {module}: {type(exc).__name__}: {exc}")
            rows.append((run_id[:8], module, "-", "UNREADABLE"))
            continue
        bad = [key for key in keys if not key[3]]
        total_keys += len(keys)
        total_bad += len(bad)
        rows.append((run_id[:8], module, str(len(keys)),
                     "0" if not bad else f"{len(bad)}: " + ", ".join(k[0] for k in bad)))
        reported_rows.append((run_id[:8], *(("<missing>" if v is None else v) for v in reported.values())))
        for key, expected, actual, ok, note in keys:
            if not ok:
                shown = "<missing>" if note == "missing key" else "<not a scalar>" if actual is None else repr(actual)
                details.append(f"MISMATCH {run_id[:8]} {module}: {key} expected {expected!r}, "
                               f"actual {shown}" + (f" ({note})" if note else ""))
            elif verbose:
                how = "exact" if expected == actual else "numeric"
                details.append(f"ok {run_id[:8]} {key} expected {expected!r} actual {actual!r}"
                               f" [{how}]" + (f" ({note})" if note else ""))
        notes += [f"{run_id[:8]} {note}" for note in run_notes]

    print(f"{'run':<8}  {'case':<34} {'keys':>4}  mismatches")
    for run_id, module, count, bad in rows:
        print(f"{run_id:<8}  {module:<34} {count:>4}  {bad}")
    print(f"{'TOTAL':<8}  {str(len(RUNS)) + ' runs':<34} {total_keys:>4}  {total_bad}")
    print(f"\n{'run':<8}  " + "  ".join(f"{key:<16}" for key in REPORT_KEYS))
    for row in reported_rows:
        print(f"{row[0]:<8}  " + "  ".join(f"{value:<16}" for value in row[1:]))
    for line in unreadable + details + notes:
        print(line)
    print(f"\n{total_bad} mismatches in {total_keys} keys across {len(RUNS) - len(unreadable)} "
          f"readable runs; {len(unreadable)} unreadable runs")
    return 2 if unreadable else 1 if total_bad or notes else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
