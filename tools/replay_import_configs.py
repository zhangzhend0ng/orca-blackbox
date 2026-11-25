"""Recheck Feishu #232's imported config presets from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
The three preset files, the three snapshots of the profile's presets and the
project saved after the selection are then read twice: with the case's own
oracle (tests/import_configs_oracle.py, fed again from the archived files)
and with the independent reader in this module. The last wants the three
files to be the config the case builds from the template's system presets,
none of the three in the profile before the import and exactly the three in
it after, nothing added or lost by the second import, every exported
parameter the stored preset carries equal to what was exported, the saved
project set to the three presets with the exported values as its effective
ones, and the plate still the template's. What analysis.json records is held
against those files and against the case log: the dialogs must say of as many
presets as the profile gained and must name the presets they ask about, the
preset lists must show the three names, the verdict and the readings must
equal what the oracle finds again, and the lists, the dialogs and the verdict
must appear in the log whose digest the receipt carries. The zip the
application imported is not harvested; only its digest is on record. Last,
each counterexample of the row is stood in for a harvested part on a
temporary copy of the run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
import ast
from copy import deepcopy
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path, PureWindowsPath
import re
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from import_configs_oracle import (ARCHIVE, DUPLICATES, ID_KEYS, IMPORTED, INI, KINDS, NAMES, RESULT_TITLE,
                                   build_config, bundle_presets, parameters, project_settings, template_presets,
                                   vendor_directory, verify_import)
from file_io_replay_support import (flattering, guards_answered, manifest, moved_project, png, project, refused,
                                    with_project_settings, work_directories)
from tools.replay_gcode_export import _same_shape

CASE = 232
TEMPLATE = ROOT / "fixtures" / "agent_layer_cube.3mf"
RESOURCES = ROOT / "resources"                # the system presets the repository carries
CLAUSES = (IMPORTED, DUPLICATES)
PRESET_FILES = {kind: f"bb_test_{kind}.json" for kind in KINDS}
START, FIRST, SECOND = "presets-start.json", "presets-first.json", "presets-second.json"
SNAPSHOTS = (START, FIRST, SECOND)
AFTER = "after-import.3mf"
REQUIRED = ("analysis.json", AFTER, *SNAPSHOTS, *PRESET_FILES.values())
WANTED = tuple(sorted((kind, NAMES[kind]) for kind in KINDS))
OVERWRITE = "Overwrite config"
COUNTED = re.compile(r"There are (\d+) configs imported")
CLASH_NAME = re.compile(r"same name:\s*(.+?)\.\s", re.I)
DIGEST = re.compile(r"[0-9a-f]{64}")
OUTCOME = re.compile(r":\s*'(PASS|FAIL)\b")
TAG = "[m7x232]"

FILE_READINGS = ("three_preset_files_named_and_typed", "config_files_match_the_template_presets",
                 "snapshots_are_preset_lists", "start_holds_none_of_the_imports", "three_presets_added_once",
                 "nothing_added_or_lost_on_the_second_import", "stored_presets_keep_the_parameters",
                 "project_selects_the_three_presets", "effective_values_match_the_export", "project_is_the_template")
RECORD_READINGS = ("recorded_case", "recorded_config_lists_the_files", "config_file_digest_recorded",
                   "dialogs_tell_what_the_profile_shows", "dropdown_rows_name_the_presets", "choosers_tell_the_files",
                   "recorded_readings_match_recomputation", "recorded_verdict_matches_readings",
                   "pictures_are_pictures", "guard_dialogs_answered", "work_directory_named_in_the_case_log",
                   "lists_and_dialogs_are_in_the_case_log", "verdict_line_is_in_the_case_log")
POSITIVE = ("manifest_sizes_and_sha256_match", *FILE_READINGS, "oracle_accepts_the_import", *RECORD_READINGS)


@lru_cache(maxsize=None)
def _template() -> bytes:
    return TEMPLATE.read_bytes()


def _loads(raw):
    """JSON from bytes, or None when it is none."""
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def _plain(value):
    """A value in one shape whatever the way it was written: a number is a number, a list of one
    item is that item, and a new line or a quote in a text is the same written as two characters or
    as itself."""
    if isinstance(value, list):
        items = [_plain(item) for item in value]
        return items[0] if len(items) == 1 else items
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    if isinstance(value, str):
        text = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace('\\"', '"').strip()
        try:
            return round(float(text), 9)
        except ValueError:
            return text
    return value


def _alike(exported, effective, kind) -> bool:
    """Whether an exported parameter and the project's effective value are one value. Filament
    values are one per extruder and only the first extruder carries the imported preset."""
    if not isinstance(exported, list):
        return _plain(exported) == _plain(effective[0] if isinstance(effective, list) and effective else effective)
    if not isinstance(effective, list) or len(effective) < len(exported):
        return False
    if kind == "filament":
        return _plain(exported[0]) == _plain(effective[0])
    return all(_plain(a) == _plain(b) for a, b in zip(exported, effective))


def _kind(data):
    if data.get("type") in KINDS:
        return data["type"]
    return next((kind for kind, key in ID_KEYS.items() if key in data), None)


def _settings(raw):
    """The effective configuration a saved project carries, or None."""
    try:
        with ZipFile(BytesIO(raw)) as bundle:
            return json.loads(bundle.read("Metadata/project_settings.config"))
    except (ValueError, KeyError, TypeError, OSError, BadZipFile):
        return None


def _rows(raw, part):
    """A snapshot of the profile's presets as a list of (kind, name, settings), or None."""
    rows = _loads(raw[part])
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get("settings"), dict)
                                            and isinstance(row.get("kind"), str) and isinstance(row.get("name"), str)
                                            for row in rows):
        return None
    return [(row["kind"], row["name"], row["settings"]) for row in rows]


def _keys(rows):
    return {(kind, name) for kind, name, _settings in rows}


def _rebuilt():
    """The config as the case builds it from the repository's system presets, and why it could not be built."""
    try:
        sources = template_presets(TEMPLATE)
        with TemporaryDirectory(prefix="replay-232-config-") as temporary:
            work = Path(temporary)
            return build_config(vendor_directory([RESOURCES], sources), sources, work, work / ARCHIVE)["presets"], None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _files(raw) -> tuple:
    """The preset files, the three snapshots and the saved project, by the independent reader.
    Returns the readings and what they were made of."""
    config = {kind: _loads(raw[part]) for kind, part in PRESET_FILES.items()}
    config = {kind: data if isinstance(data, dict) and data.get("name") == NAMES[kind] and _kind(data) == kind
              else None for kind, data in config.items()}
    rows = {part: _rows(raw, part) for part in SNAPSHOTS}
    settings = _settings(raw[AFTER])
    rebuilt, why = _rebuilt()
    held = {(kind, name): third for kind, name, third in rows[FIRST]} if rows[FIRST] is not None else {}
    stored = {f"{kind}/{name}": _held(held[(kind, name)], config[kind])
              for kind, name in WANTED if (kind, name) in held and config[kind] is not None}
    effective = {f"{kind}/{name}": _effective(config[kind], settings, kind)
                 for kind, name in WANTED if config[kind] is not None and isinstance(settings, dict)}
    return {
        "three_preset_files_named_and_typed": all(config[kind] is not None for kind in KINDS),
        "config_files_match_the_template_presets": rebuilt is not None and all(
            config[kind] == rebuilt[kind] for kind in KINDS),
        "snapshots_are_preset_lists": all(rows[part] for part in SNAPSHOTS),
        "start_holds_none_of_the_imports": rows[START] is not None and not set(WANTED) & _keys(rows[START]),
        "three_presets_added_once": rows[START] is not None and rows[FIRST] is not None
        and _keys(rows[FIRST]) - _keys(rows[START]) == set(WANTED),
        "nothing_added_or_lost_on_the_second_import": rows[FIRST] is not None and rows[SECOND] is not None
        and _keys(rows[SECOND]) == _keys(rows[FIRST]),
        "stored_presets_keep_the_parameters": len(stored) == len(WANTED) and not any(
            row["differing"] for row in stored.values()),
        "project_selects_the_three_presets": isinstance(settings, dict) and _selected(settings) == dict(
            zip(KINDS, (NAMES[kind] for kind in KINDS))),
        "effective_values_match_the_export": len(effective) == len(WANTED) and not any(
            row["changed"] for row in effective.values()),
        "project_is_the_template": _same_shape(project(raw[AFTER]), project(_template())),
    }, {"stored": stored, "effective": effective, "selected": _selected(settings) if isinstance(settings, dict) else None,
        "config_rebuilt": None if why else "from the repository's system presets", "config_rebuild_error": why,
        "not_carried": {label: len(row["not_carried"]) for label, row in stored.items()}}


def _held(settings, exported) -> dict:
    """How a stored preset holds the exported parameters: how many it carries, which it does not, and
    which of those it carries differ."""
    wanted = parameters(exported)
    missing = sorted(key for key in wanted if key not in settings)
    differing = sorted(key for key, value in wanted.items()
                       if key in settings and _plain(value) != _plain(settings[key]))
    return {"compared": len(wanted) - len(missing), "not_carried": missing, "differing": differing}


def _effective(exported, settings, kind) -> dict:
    """The exported parameters the saved project carries, and which of them differ from it."""
    wanted = parameters(exported)
    present = [key for key in wanted if key in settings]
    return {"compared": len(present), "changed": sorted(
        key for key in present if not _alike(wanted[key], settings[key], kind))}


def _selected(settings) -> dict:
    ids = settings.get("filament_settings_id")
    return {"machine": settings.get("printer_settings_id"), "process": settings.get("print_settings_id"),
            "filament": ids[0] if isinstance(ids, list) and ids else ids}


def _dialogs(analysis, stage) -> list:
    """The dialogs a stage recorded, as the objects among them."""
    block = analysis.get(stage)
    dialogs = block.get("dialogs") if isinstance(block, dict) else None
    return [row for row in dialogs if isinstance(row, dict)] if isinstance(dialogs, list) else []


def _says(dialog, title) -> bool:
    return isinstance(dialog.get("title"), str) and title in dialog["title"]


def _counted(dialogs) -> list:
    """How many configs the Import result dialogs of a stage say were imported."""
    return [int(COUNTED.search(dialog.get("message") or "").group(1)) for dialog in dialogs
            if _says(dialog, RESULT_TITLE) and COUNTED.search(dialog.get("message") or "")]


def _is_picture(raw) -> bool:
    try:
        facts = png(raw)
    except ValueError:
        return False
    return facts["format"] == "PNG" and facts["gray_levels"] >= 32 and facts["std"] >= 5


def _literal(text):
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError):
        return None


def _logged_lists(log, dropdowns) -> bool:
    """Whether the case log printed the rows of each preset list as the record holds them."""
    for kind in KINDS:
        read = dropdowns.get(kind).get("rows") if isinstance(dropdowns.get(kind), dict) else None
        lines = [line for line in log.splitlines() if line.startswith(f"{TAG} {kind} list: ")]
        if not isinstance(read, list) or len(lines) != 1 or _literal(lines[0].split(": ", 1)[1]) != read:
            return False
    return True


def _logged_dialogs(log, analysis) -> bool:
    """Whether the case log printed each recorded dialog, in order, with its title."""
    printed = [line[len(f"{TAG} dialog "):] for line in log.splitlines() if line.startswith(f"{TAG} dialog ")]
    dialogs = [row for row in (analysis.get("dialogs") if isinstance(analysis.get("dialogs"), list) else [])
               if isinstance(row, dict)]
    if len(printed) != len(dialogs):
        return False
    return all(isinstance(record, dict) and record.get("title") == dialog.get("title")
               for record, dialog in zip((_literal(line) for line in printed), dialogs))


def _logged_verdicts(log):
    """The outcome the case log's verdict line names for each clause, in the record's order. A failure's
    text holds quotes and garbled clause names, so only PASS or FAIL is read."""
    lines = [line for line in log.splitlines() if line.startswith(f"{TAG} {{")]
    return OUTCOME.findall(lines[0]) if len(lines) == 1 else None


def _record(analysis, raw, work, log, oracle) -> dict:
    """What the GUI recorded, held against the files, against the oracle's reading and against the case log."""
    config = [[kind, NAMES[kind]] for kind in KINDS]
    rows = {part: _rows(raw, part) for part in SNAPSHOTS}
    added = None
    if rows[START] is not None and rows[FIRST] is not None:
        added = len(_keys(rows[FIRST]) - _keys(rows[START]))
    first, second, ini = (_dialogs(analysis, stage) for stage in ("first", "second", "ini_attempt"))
    prompts = [dialog for dialog in second if _says(dialog, OVERWRITE)]
    asked = sorted(match.group(1).strip() for match in
                   (CLASH_NAME.search(dialog.get("message") or "") for dialog in prompts) if match)
    dropdowns = analysis.get("dropdowns") if isinstance(analysis.get("dropdowns"), dict) else {}
    choosers = [row for row in (analysis.get("choosers") if isinstance(analysis.get("choosers"), list) else [])
                if isinstance(row, dict)]
    one, two = oracle.get("first") or {}, oracle.get("second") or {}
    results = analysis.get("results")
    recorded = [results.get(clause) for clause in CLAUSES] if isinstance(results, dict) else None
    recorded_file = analysis.get("config_file") if isinstance(analysis.get("config_file"), dict) else {}
    listed = [name for name in raw if name.lower().endswith(".png")]
    return {
        "recorded_case": analysis.get("case") == CASE,
        "recorded_config_lists_the_files": sorted(map(list, analysis.get("config") or [])) == sorted(
            config) if isinstance(analysis.get("config"), list) else False,
        # the zip the application imported is not harvested: only its digest is on record
        "config_file_digest_recorded": recorded_file.get("not_harvested") is True
        and type(recorded_file.get("bytes")) is int and recorded_file["bytes"] > 0
        and isinstance(recorded_file.get("sha256"), str) and bool(DIGEST.fullmatch(recorded_file["sha256"])),
        "dialogs_tell_what_the_profile_shows": added is not None and _counted(first) == [added]
        and _counted(second) == [len(config)] and asked == sorted(NAMES[kind] for kind in KINDS)
        and len(prompts) == len(config) and _counted(ini) == [0],
        "dropdown_rows_name_the_presets": all(
            isinstance(dropdowns.get(kind), dict) and isinstance(dropdowns[kind].get("rows"), list)
            and any(NAMES[kind].casefold() in str(text).casefold() for text in dropdowns[kind]["rows"])
            and dropdowns[kind].get("selected") is True
            and NAMES[kind].casefold() in str(dropdowns[kind].get("after", "")).casefold() for kind in KINDS),
        "choosers_tell_the_files": len(work) == 1 and [row.get("file") for row in choosers] == [INI, ARCHIVE, ARCHIVE]
        and all(PureWindowsPath(str(chooser.get("entered"))) == PureWindowsPath(work[0]) / name
                for chooser, name in zip(choosers, (INI, f"inputs/{ARCHIVE}", f"inputs/{ARCHIVE}"))),
        "recorded_readings_match_recomputation": bool(oracle) and analysis.get("first_import") == one.get("reading")
        and analysis.get("second_import") == two.get("reading"),
        "recorded_verdict_matches_readings": recorded == [one.get(IMPORTED), two.get(DUPLICATES)] == ["PASS", "PASS"],
        "pictures_are_pictures": bool(listed) and all(_is_picture(raw[name]) for name in listed),
        "guard_dialogs_answered": guards_answered(analysis, raw, set(raw), log),
        "work_directory_named_in_the_case_log": bool(work),
        "lists_and_dialogs_are_in_the_case_log": _logged_lists(log, dropdowns) and _logged_dialogs(log, analysis),
        "verdict_line_is_in_the_case_log": recorded is not None and _logged_verdicts(log) == [
            str(value).partition("(")[0].strip() for value in recorded],
    }


def _oracle(analysis, raw, paths) -> dict:
    """The case's oracle fed again from the archived files, as the case fed it. Empty when it cannot read them."""
    try:
        config = [row for part in sorted(PRESET_FILES.values()) for row in bundle_presets(paths[part])]
        before, after, again = (_loads(raw[part]) for part in SNAPSHOTS)
        effective = _settings(raw[AFTER]) if analysis.get("effective_read") == "ok" else None
        one = verify_import(config, before, after, _dialogs(analysis, "first"), analysis.get("dropdowns"), effective,
                            project_settings(TEMPLATE), analysis.get("effective_read"))
        two = verify_import(config, after, again, _dialogs(analysis, "second"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, BadZipFile):
        return {}
    # tuples become lists, as the record holds them
    return json.loads(json.dumps({"first": one, "second": two}))


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings and the raw artifacts."""
    entries = manifest(directory, prefix)
    listed = sorted({entry["part"] for entry in entries})
    missing = sorted(set(REQUIRED) - set(listed))
    if missing:
        raise ValueError(f"the harvest lacks {missing}")
    try:
        paths = {part: verified_part(directory, prefix, entries, part) for part in listed}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"a listed part could not be read ({type(exc).__name__})") from exc
    analysis = _loads(raw["analysis.json"])
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    oracle = _oracle(analysis, raw, paths)
    checks, readings = _files(raw)
    checks["manifest_sizes_and_sha256_match"] = True
    checks["oracle_accepts_the_import"] = bool(oracle) and oracle["first"][IMPORTED] == "PASS" \
        and oracle["second"][DUPLICATES] == "PASS"
    checks.update(_record(analysis, raw, work_directories(log, "m7x232"), log, oracle))
    dropped = sorted(set(POSITIVE) - set(checks))
    if dropped:
        raise ValueError(f"readings dropped: {dropped}")
    report = {"oracle": oracle, "independent": readings, "work_directories": work_directories(log, "m7x232"),
              "results": analysis.get("results"), "failed": [key for key in POSITIVE if checks[key] is not True]}
    return checks, report, raw


# --- counterexamples --------------------------------------------------------------

def _encoded(value) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")


def _rewritten(record: bytes, analysis) -> bytes:
    return _encoded(analysis)


def _without(rows, kind):
    return [row for row in rows if (row.get("kind"), row.get("name")) != (kind, NAMES[kind])]


def _with(rows, stored, kind, name=None):
    """The snapshot with one preset of `stored` added, under another name when `name` is given."""
    row = deepcopy(next(row for row in stored if row.get("kind") == kind))
    if name:
        row["name"] = name
    return list(rows) + [row]


def _bumped(value):
    """A number turned into the next one, in the shape it was written; anything else into another text."""
    if isinstance(value, list):
        return [_bumped(item) for item in value]
    if isinstance(value, bool) or value is None:
        return 1
    if isinstance(value, (int, float)):
        return value + 1
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value) + " changed"
    return f"{number + 1:.{len(value.partition('.')[2])}f}" if "." in value else str(int(number) + 1)


def _key(raw, kind):
    """The first parameter of a preset file that the stored preset carries and the saved project
    carries as a number."""
    held = next((third for k, name, third in _rows(raw, FIRST) or [] if (k, name) == (kind, NAMES[kind])), {})
    settings = _settings(raw[AFTER])
    return next(key for key, value in parameters(_loads(raw[PRESET_FILES[kind]])).items()
                if key in held and key in settings and isinstance(_plain(value), float)
                and isinstance(_plain(held[key]), float) and isinstance(_plain(settings[key]), float))


def _select_template(settings):
    """The saved project set back to the presets the template names."""
    template = project_settings(TEMPLATE)
    for key in ("printer_settings_id", "print_settings_id", "filament_settings_id"):
        settings[key] = template[key]


def _with_message(analysis, stage, text):
    """The analysis with the Import result dialog of a stage saying `text`."""
    analysis = deepcopy(analysis)
    for dialog in _dialogs(analysis, stage):
        if _says(dialog, RESULT_TITLE):
            dialog["message"] = COUNTED.sub(text, dialog.get("message") or "")
    return analysis


def _stand_ins(raw) -> dict:
    """Each counterexample of the row: {label: the parts stood in for harvested ones and how}, each
    meant for `refused` on a copy whose manifest agrees with the stand-in."""
    record, analysis = raw["analysis.json"], _loads(raw["analysis.json"])
    start, first, second = (_loads(raw[part]) for part in SNAPSHOTS)
    process = _loads(raw[PRESET_FILES["process"]])
    key = _key(raw, "machine")
    replace = {
        # the profile lacks one of the three after the import, whichever it is
        **{f"preset_{kind}_missing_after_import_rejected": {FIRST: _encoded(_without(first, kind))}
           for kind in KINDS},
        "preset_value_changed_rejected": {FIRST: _encoded(_changed(first, "machine", key))},
        # the three presets were in the profile before the import, as if the .ini had been loaded
        "already_present_before_the_import_rejected": {
            START: _encoded(list(start) + [deepcopy(row) for row in first if row.get("name") in NAMES.values()])},
        # a fourth preset after the second import, as a rename on clash would leave
        "preset_renamed_on_clash_rejected": {SECOND: _encoded(_with(second, first, "machine", NAMES["machine"] + " (1)"))},
        "profile_emptied_on_the_second_import_rejected": {SECOND: b"[]"},
        "config_file_not_standalone_rejected": {PRESET_FILES["process"]: _encoded(dict(process, inherits="fdm_process_U1"))},
        # a preset file under another name than the one the case gives it
        "preset_file_renamed_rejected": {PRESET_FILES["machine"]: _encoded(dict(
            _loads(raw[PRESET_FILES["machine"]]), name="Another Printer"))},
        "wrong_preset_selected_rejected": {AFTER: with_project_settings(raw[AFTER], _select_template)},
        "effective_value_changed_rejected": {AFTER: with_project_settings(
            raw[AFTER], lambda settings: settings.__setitem__(key, _bumped(settings[key])))},
        "template_geometry_changed_rejected": {AFTER: moved_project(raw[AFTER], dx=40.0)},
        # a second import that showed no name-clash prompt
        "no_clash_prompt_rejected": {"analysis.json": _rewritten(record, dict(analysis, second=dict(
            analysis["second"], dialogs=[row for row in _dialogs(analysis, "second") if not _says(row, OVERWRITE)])))},
        # the first import said of fewer presets than the profile gained
        "result_count_disagrees_rejected": {"analysis.json": _rewritten(record, _with_message(
            analysis, "first", "There are 2 configs imported"))},
        # a preset list without the imported name
        "dropdown_row_missing_rejected": {"analysis.json": _rewritten(record, dict(analysis, dropdowns={
            kind: dict(read, rows=[text for text in read.get("rows", [])
                                  if NAMES[kind].casefold() not in str(text).casefold()])
            for kind, read in analysis["dropdowns"].items()}))},
        "chooser_path_elsewhere_rejected": {"analysis.json": _rewritten(record, dict(analysis, choosers=[
            analysis["choosers"][0], dict(analysis["choosers"][1], entered=str(PureWindowsPath(r"C:\elsewhere") / ARCHIVE)),
            *analysis["choosers"][2:]]))},
        # a record that claims both clauses over a profile that lacks one preset
        "flattering_record_rejected": {FIRST: _encoded(_without(first, "process")),
                                       "analysis.json": flattering(record, CLAUSES)},
        # the collector that recorded one file and kept another
        "manifest_mismatch_rejected": {"replace": {AFTER: b""}, "keep_manifest": False},
    }
    return {label: how if "replace" in how else {"replace": how} for label, how in replace.items()}


def _changed(rows, kind, key):
    """The snapshot with one parameter of the imported preset of `kind` changed."""
    rows = deepcopy(rows)
    row = next(row for row in rows if (row.get("kind"), row.get("name")) == (kind, NAMES[kind]))
    row["settings"][key] = _bumped(row["settings"].get(key, 0))
    return rows


def _controls(directory, prefix, raw):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    return {label: refused(_read, POSITIVE, directory, prefix, **how)
            for label, how in _stand_ins(raw).items()}


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #232 harvest after the driver verified its log."""
    checks, report, raw = _read(directory, prefix)
    result = {"checks": checks, "import_configs": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, raw))
    return result
