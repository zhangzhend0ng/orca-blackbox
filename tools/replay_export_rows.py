"""Recheck Feishu #238's disabled export rows from a verified harvest.

The manifest's byte count and SHA-256 are checked for every artifact first.
The verdict of the case rests on two readings of the File > Export menu, one
before slicing and one after it, and both live in analysis.json only: on the
guest the Export submenu did not open on screen, so no picture was kept. The
replay reads those rows a second time, with the independent reader in this
module, and a third time with the case's own oracle
(export_rows_expectation_gaps). The three slice export rows must be on the
menu once each and disabled before slicing, then enabled after it; the
control rows must be enabled both times; and the menu must list the same
rows in the same order both times, for a reading that dropped a row is no
reading. The rows are then held against the receipt-hashed case log, which
printed each reading as it was taken, against the reading the slice wait took
when the Export G-code row turned enabled, and against the order of the
case's stages. The project saved before slicing must be the standard cube
and must carry no plate G-code, as a project saved before slicing does. What
the record says of the fixture, the presets and the plate may not outrun that
project, and its gaps and verdict may not outrun the readings. Last, each
counterexample of the row is stood in for a harvested part on a temporary
copy of the run and must be refused.

    python tools/replay_case_evidence.py <prefix>-receipt.json
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from export_io_oracle import export_rows_expectation_gaps
from file_io_replay_support import (blank_png, changed_share, emptied, flattering, guard_dialogs, guard_parts,
                                    guards_answered, manifest, moved_project, png, presets_match, project,
                                    refused, screenshots, sliced, work_directories, zipped)
from tools.replay_gcode_export import FROM_FIXTURE, _as_loaded, _same_shape

CASE = 238
FIXTURE = ROOT / "fixtures" / "feishu_std_cube.3mf"
SUFFIX = "(" + FIXTURE.name + ")"     # what the application appended to a preset ID when it opened the fixture
PICTURES = ("before.png", "sliced.png")
CLAUSES = ("切片导出类条目置灰", "切片完成后恢复可用")
SLICE_ROWS = ("Export plate sliced file", "Export all plate sliced file", "Export G-code")
CONTROL_ROWS = ("Export all objects as one STL", "Export Generic 3MF")
# the stages of the case in the order the expectation needs them: the menu read before slicing,
# the slice, and the menu read after it
STAGES = ("observe_before_slice", "slice", "observe_after_slice")
CHANGED = 0.01     # slicing repaints a fifth of the window on the archived runs; a copied screenshot changes none
READ_LINE = re.compile(r"^\[export\] File > Export read: (\[.*\])(?:; picture unavailable:.*)?$", re.M)
SIGNAL_LINE = re.compile(r"^\[export\] 'Export G-code' enabled (\S+?)s after the Slice click$", re.M)
GAPS_LINE = re.compile(r"^\[m7x238\] gaps (\{.*\})\s*$", re.M)
LIST = re.compile(r"\[[^\]]*\]")
MENU_READINGS = ("slice_rows_disabled_before_slicing", "slice_rows_enabled_after_slicing",
                 "control_rows_enabled_throughout", "same_menu_both_times", "file_menu_offers_export_both_times",
                 "slice_reading_agrees_with_after_menu")
RECORD_READINGS = ("recorded_case", "recorded_fixture_matches_file", "recorded_presets_match_project",
                   "recorded_objects_match_project", "recorded_gaps_match_recomputation",
                   "recorded_verdict_matches_gaps", "menus_were_read_around_the_slice", "editor_left_running",
                   "guard_dialogs_answered", "menus_are_in_the_case_log", "slice_signal_is_in_the_case_log",
                   "gaps_line_is_in_the_case_log", "work_directory_named_in_the_case_log")
POSITIVE = ("manifest_sizes_and_sha256_match", "before_project_is_the_fixture", "before_project_is_not_sliced",
            "plate_holds_a_model", "before_is_sliced_as_recorded", *MENU_READINGS, "oracle_accepts_the_menus",
            *RECORD_READINGS, "screenshots_are_pictures", "sliced_view_differs_from_before")


@lru_cache(maxsize=1)
def _fixture():
    return FIXTURE.read_bytes()


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _block(analysis, key):
    """A recorded block that is an object, or an empty one."""
    value = analysis.get(key)
    return value if isinstance(value, dict) else {}


def _rows(analysis, stage, key):
    """The rows a stage recorded under `key`, as a list or None."""
    rows = _block(analysis, stage).get(key)
    return rows if isinstance(rows, list) else None


def _name(label):
    """A menu row's name: its text without the shortcut and the dots, in lower case."""
    return label.partition("\t")[0].rstrip(".…").strip().casefold()


def _menu(rows):
    """A recorded menu as (name, enabled) rows; None when it is no list of rows with a text and a state each."""
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get("label"), str)
                                            and isinstance(row.get("enabled"), bool) for row in rows):
        return None
    return [(_name(row["label"]), row["enabled"]) for row in rows]


def _found(menu, name):
    """The enabled states of the rows named `name`, in the order the menu lists them."""
    return [enabled for row, enabled in menu if row == name.casefold()]


def _menus(analysis) -> dict:
    """The readings of the File > Export menu by the independent reader: before slicing, after it, and
    the one the slice wait took when the Export G-code row turned enabled."""
    first, second = _menu(_rows(analysis, "menu_before_slice", "export")), _menu(_rows(analysis, "menu_after_slice", "export"))
    waited = _menu(_rows(analysis, "slice", "export_menu_after"))
    if first is None or second is None:
        return dict.fromkeys(MENU_READINGS, False)
    file_before, file_after = _menu(_rows(analysis, "menu_before_slice", "file")), _menu(_rows(analysis, "menu_after_slice", "file"))
    return {
        "slice_rows_disabled_before_slicing": all(_found(first, name) == [False] for name in SLICE_ROWS),
        "slice_rows_enabled_after_slicing": all(_found(second, name) == [True] for name in SLICE_ROWS),
        "control_rows_enabled_throughout": all(_found(menu, name) == [True]
                                              for menu in (first, second) for name in CONTROL_ROWS),
        # the same rows in the same order, none of them twice: a reading that dropped a row is no reading
        "same_menu_both_times": [row for row, _ in first] == [row for row, _ in second]
        and len({row for row, _ in first}) == len(first),
        "file_menu_offers_export_both_times": file_before is not None and file_after is not None and all(
            _found(menu, "Export") == [True] for menu in (file_before, file_after)),
        "slice_reading_agrees_with_after_menu": waited is not None and waited == second,
    }


def _project(analysis, raw) -> dict:
    """The project saved before slicing: the standard cube, holding a model and no plate G-code."""
    saved, fixture = project(raw["before.3mf"]), project(_fixture())
    return {
        "before_project_is_the_fixture": _same_shape(saved, fixture) and all(
            _as_loaded(saved["settings"].get(key), SUFFIX) == _as_loaded(fixture["settings"].get(key), SUFFIX)
            for key in FROM_FIXTURE),
        "before_project_is_not_sliced": not sliced(raw["before.3mf"])["gcode_members"],
        "plate_holds_a_model": bool(saved["objects"]) and len({item["plate"] for item in saved["objects"]}) == 1,
        "before_is_sliced_as_recorded": analysis.get("before_is_sliced") is False,
    }


def _started(timings, stage):
    try:
        return datetime.fromisoformat(timings[stage]["started_utc"])
    except (KeyError, TypeError, ValueError):
        return None


def _ordered(timings) -> bool:
    """Whether the case's stages ran in the order the expectation needs: the menu was read before the
    slice, and read again only after it."""
    first, second, third = (_started(timings, stage) for stage in STAGES)
    return None not in (first, second, third) and first <= second <= third


def _printed(text):
    """A list as the case log printed it, or None when it does not parse."""
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError):
        return None
    return value if isinstance(value, list) else None


def _logged_menus(log, analysis) -> bool:
    """Whether the receipt-hashed case log printed the two menu readings as the record holds them, the
    one before slicing first."""
    printed = []
    for text in READ_LINE.findall(log):
        rows = _printed(text)
        if rows is None or not all(isinstance(row, tuple) and len(row) == 3 for row in rows):
            return False
        printed.append([(str(label).partition("\t")[0], enabled) for _index, label, enabled in rows])
    recorded = []
    for stage in ("menu_before_slice", "menu_after_slice"):
        rows = _rows(analysis, stage, "export")
        if _menu(rows) is None:
            return False
        recorded.append([(row["label"].partition("\t")[0], row["enabled"]) for row in rows])
    return printed == recorded and len(printed) == 2


def _as_printed(rows):
    """A recorded menu as the log prints it: (label without the shortcut, enabled), or None."""
    menu = _menu(rows)
    return None if menu is None else [(row["label"].partition("\t")[0], row["enabled"]) for row in rows]


def _logged_signal(log, analysis) -> bool:
    """Whether the case log told of the Export G-code row turning enabled after as many seconds as the record holds."""
    told = SIGNAL_LINE.findall(log)
    waited = _number(_block(analysis, "slice").get("export_enabled_after_seconds"))
    return len(told) == 1 and waited is not None and waited > 0 and _number(told[0]) == waited


def _logged_gaps(log, gaps) -> bool:
    """Whether the case log's gaps line lists the failures of each clause as the oracle finds them. The
    clause names come out garbled in the log; the lists after them do not."""
    lines = GAPS_LINE.findall(log)
    if len(lines) != 1 or gaps is None:
        return False
    printed = [_printed(text) for text in LIST.findall(lines[0])]
    return None not in printed and printed == [gaps[clause] for clause in CLAUSES]


def _record(analysis, raw, gaps, log, work, kept) -> dict:
    """What the GUI recorded, held against the files, against the readings and against the case log."""
    saved = project(raw["before.3mf"])
    results, recorded = analysis.get("results"), analysis.get("expectation_gaps")
    return {
        "recorded_case": analysis.get("case") == CASE,
        "recorded_fixture_matches_file": analysis.get("fixture") == {
            "name": FIXTURE.name, "bytes": len(_fixture()), "sha256": sha256(_fixture()).hexdigest()},
        "recorded_presets_match_project": presets_match(analysis.get("presets"), saved["settings"]),
        "recorded_objects_match_project": analysis.get("plate_objects") == sorted(
            item["name"] for item in saved["objects"]),
        "recorded_gaps_match_recomputation": gaps is not None and recorded == gaps,
        "recorded_verdict_matches_gaps": isinstance(results, dict) and isinstance(recorded, dict)
        and [results.get(clause) for clause in CLAUSES] == ["PASS"] * len(CLAUSES) and gaps is not None
        and recorded == gaps and not any(gaps.values()),
        "menus_were_read_around_the_slice": _ordered(analysis.get("timings")),
        "editor_left_running": analysis.get("editor_after_case") == {"alive": True, "dialog": None},
        "guard_dialogs_answered": guards_answered(analysis, raw, kept, log),
        "menus_are_in_the_case_log": _logged_menus(log, analysis),
        "slice_signal_is_in_the_case_log": _logged_signal(log, analysis),
        "gaps_line_is_in_the_case_log": _logged_gaps(log, gaps),
        "work_directory_named_in_the_case_log": bool(work),
    }


def _read(directory, prefix):
    """Every offline reading of one harvest.

    Raises ValueError when an artifact fails its manifest entry or cannot be read. Returns the
    checks, the readings and the raw artifacts."""
    entries = manifest(directory, prefix)
    record = verified_part(directory, prefix, entries, "analysis.json").read_bytes()
    analysis = json.loads(record.decode("utf-8-sig"))
    if not isinstance(analysis, dict):
        raise ValueError("analysis.json: expected an object")
    listed = {entry["part"] for entry in entries}
    parts = ["before.3mf", *PICTURES, *(part for part in guard_parts(analysis, listed) if part not in PICTURES)]
    try:
        paths = {part: verified_part(directory, prefix, entries, part) for part in parts}
        raw = {part: path.read_bytes() for part, path in paths.items()}
        log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"a listed part could not be read ({type(exc).__name__})") from exc
    raw["analysis.json"] = record
    before, after = _rows(analysis, "menu_before_slice", "export"), _rows(analysis, "menu_after_slice", "export")
    # the case's own oracle judges the recorded rows whenever they are rows; the reader above judges them again
    gaps = export_rows_expectation_gaps(before, after) if _menu(before) is not None and _menu(after) is not None else None
    shot = screenshots({part: raw[part] for part in PICTURES}, None, PICTURES, PICTURES[0])
    share = changed_share(raw["before.png"], raw["sliced.png"])
    checks = {"manifest_sizes_and_sha256_match": True, **_project(analysis, raw), **_menus(analysis),
              "oracle_accepts_the_menus": gaps is not None and not any(gaps.values()),
              **_record(analysis, raw, gaps, log, work_directories(log, "m7x238"), set(parts)),
              "screenshots_are_pictures": shot["screenshots_are_pictures"],
              "sliced_view_differs_from_before": share is not None and share >= CHANGED}
    dropped = sorted(set(POSITIVE) - set(checks))
    if dropped:
        raise ValueError(f"readings dropped: {dropped}")
    report = {"menu": {"before": _as_printed(before), "after": _as_printed(after),
                       "when_the_wait_ended": _as_printed(_rows(analysis, "slice", "export_menu_after"))},
              "export_enabled_after_seconds": _block(analysis, "slice").get("export_enabled_after_seconds"),
              "guard_dialogs": len(guard_dialogs(analysis)), "screen_change": share,
              "oracle_gaps": gaps, "failed": [key for key in POSITIVE if checks[key] is not True]}
    return checks, report, raw


# --- counterexamples --------------------------------------------------------------

def _rewritten(record: bytes, analysis) -> bytes:
    return json.dumps(analysis, indent=2, ensure_ascii=False).encode("utf-8")


def _touched(analysis, stage, key, name, **changes):
    """The analysis with one row of the Export menu changed: a copy throughout."""
    analysis = deepcopy(analysis)
    for row in analysis[stage][key]:
        if _name(row["label"]) == name.casefold():
            row.update(changes)
            break
    return analysis


def _without_row(analysis, stage, name):
    analysis = deepcopy(analysis)
    analysis[stage]["export"] = [row for row in analysis[stage]["export"] if _name(row["label"]) != name.casefold()]
    return analysis


def _twice(analysis, stage, name):
    analysis = deepcopy(analysis)
    rows = analysis[stage]["export"]
    position = next(index for index, row in enumerate(rows) if _name(row["label"]) == name.casefold())
    rows.insert(position, deepcopy(rows[position]))
    return analysis


def _reordered(analysis, stage):
    analysis = deepcopy(analysis)
    analysis[stage]["export"].reverse()
    return analysis


def _without_export(analysis, stage):
    """The analysis with the Export row taken out of the File menu read at `stage`."""
    analysis = deepcopy(analysis)
    analysis[stage]["file"] = [row for row in analysis[stage]["file"] if _name(row["label"]) != "export"]
    return analysis


def _size(raw: bytes) -> tuple:
    """A picture's (width, height)."""
    shown = png(raw)
    return shown["width"], shown["height"]


def _stand_ins(record: bytes, raw: dict) -> dict:
    """Each counterexample of the row: {label: the parts stood in for harvested ones and how}, each
    meant for `refused` on a copy whose manifest agrees with the stand-in."""
    analysis = json.loads(record.decode("utf-8-sig"))
    unsliced = sliced(raw["before.3mf"])["members"]
    stand_ins = {
        # one slice export row enabled before slicing: the first clause cannot have passed
        "slice_row_enabled_before_slicing_rejected": {"analysis.json": _rewritten(record, _touched(
            analysis, "menu_before_slice", "export", "Export plate sliced file", enabled=True))},
        # one still disabled after slicing: the second clause cannot have passed
        "slice_row_still_disabled_after_slicing_rejected": {"analysis.json": _rewritten(record, _touched(
            analysis, "menu_after_slice", "export", "Export G-code", enabled=False))},
        "menu_after_slice_missing_rejected": {"analysis.json": _rewritten(
            record, {key: value for key, value in analysis.items() if key != "menu_after_slice"})},
        "menu_rows_incomplete_rejected": {"analysis.json": _rewritten(
            record, _without_row(analysis, "menu_after_slice", "Export all plate sliced file"))},
        "slice_row_duplicated_rejected": {"analysis.json": _rewritten(
            record, _twice(analysis, "menu_before_slice", "Export G-code"))},
        # a control row disabled: the menu was not readable as the case needs it
        "control_row_disabled_rejected": {"analysis.json": _rewritten(
            record, _touched(analysis, "menu_before_slice", "export", "Export Generic 3MF", enabled=False))},
        "menus_differ_between_reads_rejected": {"analysis.json": _rewritten(
            record, _reordered(analysis, "menu_after_slice"))},
        # the File menu read after slicing offers no Export row: the Export menu did not come from it
        "file_menu_without_export_rejected": {"analysis.json": _rewritten(
            record, _without_export(analysis, "menu_after_slice"))},
        # the slice wait's own reading of the menu tells another story than the one read after it
        "slice_reading_disagrees_rejected": {"analysis.json": _rewritten(record, _touched(
            analysis, "slice", "export_menu_after", "Export plate sliced file", enabled=False))},
        # a record that claims both clauses over a menu that had a slice row enabled before slicing
        "flattering_record_rejected": {"analysis.json": flattering(_rewritten(record, _touched(
            analysis, "menu_before_slice", "export", "Export G-code", enabled=True)), CLAUSES)},
        "gaps_edited_rejected": {"analysis.json": _rewritten(record, dict(analysis, expectation_gaps=dict(
            analysis["expectation_gaps"], **{CLAUSES[0]: ["before slicing: 'Export G-code' is enabled"]})))},
        "editor_left_broken_rejected": {"analysis.json": _rewritten(
            record, dict(analysis, editor_after_case={"alive": False, "dialog": None}))},
        "fixture_edited_rejected": {"analysis.json": _rewritten(
            record, dict(analysis, fixture=dict(analysis["fixture"], sha256="0" * 64)))},
        "presets_edited_rejected": {"analysis.json": _rewritten(
            record, dict(analysis, presets=dict(analysis["presets"], layer_height="0.3")))},
        "guard_left_open_rejected": {"analysis.json": flattering(record, CLAUSES, memory_guard_dialogs=[{
            "title": "Memory Usage Warning", "texts": ["Yes, Continue", "No, Stop"], "closed": False,
            "screenshot": "memory-guard-0.png", "image": {"width_px": 796, "height_px": 216}}])},
        # the project saved "before slicing" already carries the plate's G-code
        "sliced_project_as_before_rejected": {
            "before.3mf": zipped(dict(unsliced, **{"Metadata/plate_1.gcode": b"; a plate G-code\n"}))},
        "another_project_rejected": {"before.3mf": moved_project(raw["before.3mf"], dx=40.0)},
        # a plate with nothing on it: the precondition asks for a model
        "empty_plate_rejected": {"before.3mf": emptied(raw["before.3mf"])},
        # the record says the plate was already sliced before the case began
        "record_says_sliced_rejected": {"analysis.json": _rewritten(record, dict(analysis, before_is_sliced=True))},
        "sliced_picture_copied_from_before_rejected": {"sliced.png": raw["before.png"]},
        # a screenshot replaced by an empty picture of the same size
        "blank_screenshot_rejected": {"before.png": blank_png(*_size(raw["before.png"]))},
        # the collector that recorded one file and kept another
        "manifest_mismatch_rejected": {"replace": {"before.3mf": b""}, "keep_manifest": False},
    }
    return {label: how if "replace" in how else {"replace": how} for label, how in stand_ins.items()}


def _reversed_stages(record: bytes) -> bytes:
    """The record with the menu "after" the slice read before the slice began: the two readings of
    the menu have swapped their start times."""
    analysis = json.loads(record.decode("utf-8-sig"))
    timings = analysis["timings"]
    timings["observe_before_slice"]["started_utc"], timings["observe_after_slice"]["started_utc"] = (
        timings["observe_after_slice"]["started_utc"], timings["observe_before_slice"]["started_utc"])
    return _rewritten(record, analysis)


def _first_menu_flipped(log: str) -> str:
    """The log with its first menu reading saying that a slice export row was enabled before slicing."""
    found = READ_LINE.search(log)
    if found is None:
        return log
    changed = found.group(0).replace(", False)", ", True)", 1)
    return log[:found.start()] + changed + log[found.end():]


@contextmanager
def _relogged(directory, prefix, edit):
    """A temporary copy of the run whose case log is passed through `edit`, as text in and text out."""
    with TemporaryDirectory(prefix="replay-log-") as temporary:
        work = Path(temporary)
        for path in Path(directory).glob(f"{prefix}-*"):
            if path.is_file():
                shutil.copyfile(path, work / path.name)
        log = work / f"{prefix}-case.log"
        log.write_text(edit(log.read_text(encoding="utf-8-sig")), encoding="utf-8")
        yield work, prefix


def _controls(directory, prefix, raw):
    """Each counterexample of the row, stood in on a copy whose manifest agrees with it."""
    record = raw["analysis.json"]
    stand_ins = _stand_ins(record, raw)
    stand_ins["stage_order_reversed_rejected"] = {"replace": {"analysis.json": _reversed_stages(record)}}
    checks = {label: refused(_read, POSITIVE, directory, prefix, **how) for label, how in stand_ins.items()}
    # the receipt-hashed log tells of a menu the record does not hold
    with _relogged(directory, prefix, _first_menu_flipped) as (folder, altered):
        try:
            readings = _read(folder, altered)[0]
            checks["menu_log_line_edited_rejected"] = not all(readings[name] for name in POSITIVE)
        except ValueError:
            checks["menu_log_line_edited_rejected"] = True
    return checks


def replay(directory: Path, prefix: str) -> dict:
    """Re-evaluate a #238 harvest after the driver verified its log."""
    checks, report, raw = _read(directory, prefix)
    result = {"checks": checks, "export_rows": report}
    if not report["failed"]:
        result["checks"].update(_controls(directory, prefix, raw))
    return result
