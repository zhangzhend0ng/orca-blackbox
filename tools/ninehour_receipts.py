"""One receipt per harvested run, for the nine-hour run of 2026-11-25.

    python -B tools/ninehour_receipts.py <harvest_root_or_run_dir> [...] [--runs <id,id,...>]
        [--ledger <path>] [--machine guest|fa706g3|mac] [--json <out_dir>]

Prints one Markdown table to stdout: machine, label, scenario, run, commit,
verdicts, guest / host / action seconds, stage sum and the stages with ok=0.
With --json it also writes <run_id>.json per run into out_dir. In a receipt
every value names in `sources` the file and key (or log line) it came from.
A source taken from a file always reads `<file>#<key or derivation>`.

Read-only: nothing under a harvest is created, changed or deleted. It starts
no GUI, no VM and no network. Standard library only.

Run directories, as the three lines write them:

  guest     artifacts/windows_mcp_harvest/<run_id>/ (runner/hv_harvest.ps1), with
            the host summary at artifacts/native_save_demo/<run_id>/summary.json
            (tools/native_save_demo.py).
  fa706g3   the same harvest layout plus native_run.log and execution_host.json
            (fa_run.py). There is no host summary and usually no teardown.json.
  mac       artifacts/mac_project_copy/<run_id>/result.json (runner/macos_project_copy.py).
            A committed evidence copy renames the file to <anything>_result.json,
            so the schema is what is recognised, not the name; a directory that
            holds several gives one receipt per result.

A harvest root is a directory of run directories: it needs --runs, and only
those ids are read. A run directory given directly is read as it is.

The machine is inferred, most specific first: the Mac result schema;
native_run.log or execution_host.json in the run directory (fa706g3); a host
summary beside the harvest root (guest). --machine replaces the inference. The
receipt keeps what the files said (identity.machine_inferred) and warns when
the two differ. identity.execution_host carries hyper_v_guest, machine and flag
from execution_host.json.

Null means not available and is never written as 0. A null that names a file
in `sources` was expected from that file, and `missing` lists the absent file
or key. Two kinds of null are not gaps: a null without a source entry does not
apply to that kind of run (a Mac run has no process.json, a fa706g3 run has no
host summary), and keys that only exist when something went wrong (an error, a
failure_stage, comparison.reason, unmet_expectations) are null and unlisted.

  seconds.guest          process.json: finished_at_ns - started_at_ns
  seconds.host_wall      host summary: host_wall_seconds, harvest_seconds
  seconds.harvest
  seconds.script_action  native_worker.json: script_action_elapsed_ns
  seconds.mac_wall       Mac result: finished_at - started_at (ISO-8601 with offsets)
  stages.list            every `[tag] <name> ok=<0|1> seconds=<n>` line of
                         native_worker.log, in order, with its line number. Any
                         single-word tag with that shape counts.
  stages.stage_sum_ok    the ok=1 stages that are not the parent of another
                         listed stage. field.<X> wraps locate.<X> and
                         edit_readback.<X> (harness/param_case_lib.py), so a
                         parent is never added to its own children. It is null
                         when the log has no stage line, and 0 only when stage
                         lines exist and none succeeded.
  artifacts              the proof.json digests against SHA-256 recomputed from
                         proof/0001.3mf and exports/0001.gcode.
                         artifact_hashes_match is null while one of them is absent.

In the table a Mac row shows its Mac wall under "host s". stdout carries only
the table; notes about missing evidence, hash mismatches and warnings, and the
errors behind exit code 2, go to stderr.

Exit codes: 0 when every receipt was produced; 2 for a malformed input (the
message names the file and the reason) or a bad argument, in which case the
receipts that could still be built are printed and written. A half-harvested
run is not an error.
"""
import argparse
import copy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

SCHEMA = "ninehour_receipt/1"
MACHINES = ("guest", "fa706g3", "mac")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")      # a run id that is also a safe file name
HARVEST_RUN_ID = re.compile(r"[0-9a-f]{32}")                # uuid4().hex: how every line names a run directory
# harness/native_preset_script.py::timed_flow_step prints "[tag] <name> ok=<0|1> seconds=<n>".
STAGE_LINE = re.compile(r"^\[([^\]\s]+)\] (.+?) ok=([01]) seconds=(\d+(?:\.\d+)?)$")
# Nesting as harness/param_case_lib.py emits it: run_ops measures "field.<label>" around
# uia_set_float, which itself measures "locate.<label>" and "edit_readback.<label>".
PARENT_PREFIX, CHILD_PREFIXES = "field", ("locate", "edit_readback")
PROJECT, GCODE = "proof/0001.3mf", "exports/0001.gcode"
WINDOWS_FILES = ("result.json", "process.json", "native_worker.json", "native_worker.log", "proof.json",
                 PROJECT, GCODE, "teardown.json")
EXECUTION_HOST, SUMMARY_DIR = "execution_host.json", "native_save_demo"
MAC_ERROR_LIMIT = 300
COLUMNS = ("machine", "label", "scenario", "run (first 8 characters)", "commit (first 7 characters)", "verdict",
           "pass", "comparison", "cleanup", "guest s", "host s", "action s", "stage sum", "stages with ok=0")
BLANK = {
    "identity": {"run_id": None, "source_commit": None, "scenario": None, "goal": None, "machine": None,
                 "machine_inferred": None, "label": None, "execution_host": None},
    "verdicts": {"release_verdict": None, "verified_pass": None, "cleanup_confirmed": None, "execution_status": None,
                 "mode": None, "comparison": None, "verdict": None, "failure_stage": None, "error": None,
                 "guest_phases": None, "wall_loops_gcode_echo": None},
    "seconds": {"guest": None, "host_wall": None, "harvest": None, "script_action": None, "mac_wall": None},
    "stages": {"list": None, "stage_sum_ok": None, "ok0": None, "parents": None, "tags": None},
    "artifacts": {"proof_run_id": None, "project_sha256": None, "project_sha256_recomputed": None,
                  "gcode_sha256": None, "gcode_sha256_recomputed": None, "artifact_hashes_match": None,
                  "teardown_active_processes": None},
}


class ReceiptError(Exception):
    """Something the operator has to fix; the message names the subject and the reason."""

    def __init__(self, subject, reason):
        super().__init__(f"{subject}: {reason}")


class MalformedInput(ReceiptError):
    """A file that is there but is not what it should be."""


class WriteFailed(ReceiptError):
    """The receipts could not be written where they were asked for."""


def read_bytes(path):
    try:
        return path.read_bytes()
    except OSError as error:
        raise MalformedInput(path, f"cannot read it ({error.strerror or error})") from None


def utf8(path, raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MalformedInput(path, f"not UTF-8 (byte 0x{raw[error.start]:02x} at offset {error.start})") from None


def split_lines(text):
    return re.split(r"\r\n|\r|\n", text)


def parse_json(path) -> dict:
    """The JSON object in `path`; anything else is a malformed input."""
    try:
        data = json.loads(utf8(path, read_bytes(path)))
    except ValueError as error:
        raise MalformedInput(path, f"invalid JSON ({error})") from None
    except RecursionError:
        raise MalformedInput(path, "JSON nested too deeply") from None
    if not isinstance(data, dict):
        raise MalformedInput(path, f"top level is {type(data).__name__}, not an object")
    return data


def check(value, kinds, where):
    """`value` when it is one of `kinds`; a bool is never accepted as a number here."""
    if isinstance(value, bool) and bool not in kinds or not isinstance(value, kinds):
        expected = " or ".join(kind.__name__ for kind in kinds)
        raise MalformedInput(where[0], f"{where[1]}: expected {expected}, got {type(value).__name__}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
        raise MalformedInput(where[0], f"{where[1]}: {value} is not a finite number")
    return value


def strings(value, where):
    return [check(item, (str,), where) for item in value]


def parse_stages(text) -> list:
    """Every `[tag] <name> ok=<0|1> seconds=<n>` line, in order, with its 1-based line number."""
    stages = []
    for number, line in enumerate(split_lines(text), 1):
        found = STAGE_LINE.match(line.rstrip())
        if found and found[2].strip():
            stages.append({"stage": found[2].strip(), "ok": int(found[3]), "seconds": float(found[4]),
                           "line": number, "tag": found[1], "text": found[4]})
    return stages


def parent_stages(stages) -> set:
    """Indexes of the stages that wrap another listed stage: field.<X> around locate.<X> / edit_readback.<X>."""
    def parts(stage):
        return stage["stage"].partition(".")

    parents = set()
    for index, stage in enumerate(stages):
        prefix, dot, suffix = parts(stage)
        if prefix == PARENT_PREFIX and dot and any(
                other is not stage and parts(other)[2] == suffix and parts(other)[0] in CHILD_PREFIXES
                for other in stages):
            parents.add(index)
    return parents


def stage_sum_ok(stages, parents) -> float | None:
    """Exact sum of the ok=1 stages that are not parents; None when there is no stage line."""
    if not stages:
        return None
    return float(sum((Decimal(stage["text"]) for index, stage in enumerate(stages)
                      if stage["ok"] and index not in parents), Decimal(0)))


def is_mac_result(data) -> bool:
    """The result written by runner/macos_project_copy.py: `verdict` beside `guest.phases`."""
    return "verdict" in data and isinstance(data.get("guest"), dict) and isinstance(data["guest"].get("phases"), dict)


def ns_seconds(path, where, finished, started):
    if finished < started:
        raise MalformedInput(path, f"{where}: finished_at_ns precedes started_at_ns")
    return (finished - started) / 10**9


def iso_seconds(path, where, finished, started):
    try:
        seconds = (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except TypeError:
        raise MalformedInput(path, f"{where}: one timestamp has a UTC offset and the other does not") from None
    except ValueError:
        raise MalformedInput(path, f"{where}: not ISO-8601 timestamps ({started!r}, {finished!r})") from None
    if seconds < 0:
        raise MalformedInput(path, f"{where}: finished_at precedes started_at")
    return seconds


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
    except OSError as error:
        raise MalformedInput(path, f"cannot read it ({error.strerror or error})") from None
    return digest.hexdigest()


def hashes_match(recorded, recomputed) -> bool | None:
    """True or False once every digest is known, None while a file is absent."""
    if None in (*recorded, *recomputed):
        return None
    return all(want.lower() == have for want, have in zip(recorded, recomputed))


def load_ledger(path) -> dict:
    """{run_id: (line number, entry)} of the session ledger; the last line written for a run wins."""
    entries = {}
    for number, line in enumerate(split_lines(utf8(path, read_bytes(path))), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as error:
            raise MalformedInput(path, f"line {number}: invalid JSON ({error})") from None
        except RecursionError:
            raise MalformedInput(path, f"line {number}: JSON nested too deeply") from None
        if not isinstance(entry, dict):
            raise MalformedInput(path, f"line {number}: not a JSON object")
        if not isinstance(entry.get("run_id"), str) or not entry["run_id"].strip():
            raise MalformedInput(path, f"line {number}: run_id is missing or not a non-empty string")
        entries[entry["run_id"]] = (number, entry)
    return entries


def first_of(sources):
    """(value, source) of the first source that has a value."""
    tried = []
    for read in sources:
        value, source = read()
        tried.append(source)
        if value is not None:
            return value, source
    return None, " or ".join(tried) + " - neither available"


def summary_path(run_dir):
    return run_dir.parent.parent / SUMMARY_DIR / run_dir.name / "summary.json"


def summary_name(run_dir):
    return f"{SUMMARY_DIR}/{run_dir.name}/summary.json"


def machine_signals(run_dir, mac_file) -> list:
    """What the files say about the machine, most specific first."""
    signals = []
    if mac_file:
        signals.append(("mac", f"{mac_file} carries the Mac runner schema"))
    for name in ("native_run.log", EXECUTION_HOST):
        if (run_dir / name).is_file():
            signals.append(("fa706g3", f"{name} exists"))
    if summary_path(run_dir).is_file():
        signals.append(("guest", f"{summary_name(run_dir)} exists"))
    return signals


class Receipt:
    """One run's receipt while it is filled in."""

    def __init__(self, run_dir, paths, expected):
        self.run_dir, self.paths, self.expected = run_dir, paths, expected
        self.data = {"schema": SCHEMA, "run_dir": str(run_dir), **copy.deepcopy(BLANK)}
        self.sources, self.missing, self.warnings, self.docs = {"run_dir": "command line"}, [], [], {}
        self.entry, self.ledger_at, self.ledger_file = None, None, None
        self.ledger_note = "no --ledger given"

    def set(self, path, value, source):
        parts = path.split(".") if isinstance(path, str) else list(path)
        node = self.data
        for name in parts[:-1]:
            if not isinstance(node.get(name), dict):
                node[name] = {}
            node = node[name]
        node[parts[-1]] = value
        self.sources[".".join(parts)] = source

    def bind_ledger(self, ledger, ledger_path, run_id):
        if ledger_path is not None:
            self.ledger_file = Path(ledger_path)
        if ledger is None or ledger_path is None:
            return
        found = ledger.get(run_id)
        if found is None:
            self.ledger_note = f"no ledger entry for run {run_id}"
            return
        self.entry, self.ledger_at = found[1], f"{ledger_path}:{found[0]}"

    def ledger_text(self, key):
        """(value, source): a non-blank string from the run's ledger line, else None."""
        if self.entry is None:
            return None, self.ledger_note
        source = f"{self.ledger_at}#{key}"
        if key not in self.entry or self.entry[key] is None:
            self.missing.append(source)
            return None, source
        value = check(self.entry[key], (str,), (self.ledger_file, source))
        return (value if value.strip() else None), source

    def machine(self, override, signals):
        inferred = signals[0][0] if signals else None
        evidence = f"inferred: {signals[0][1]}" if signals else "no machine signal in the directory"
        self.set("identity.machine", override or inferred, f"--machine {override}" if override else evidence)
        self.set("identity.machine_inferred", inferred, evidence)
        if override and inferred and override != inferred:
            self.warnings.append(
                f"--machine {override} replaces {inferred}, which is what the files say ({signals[0][1]})")

    def document(self, name):
        if name not in self.docs:
            if not self.paths[name].is_file():
                if name in self.expected:
                    self.missing.append(name)
                self.docs[name] = None
            else:
                self.docs[name] = parse_json(self.paths[name])
        return self.docs[name]

    def pick(self, name, key, *kinds, optional=False):
        """The value at file `name`, key `key` (dotted keys descend into objects); None when absent."""
        data = self.document(name)
        if data is None:
            return None
        parts = key.split(".") if isinstance(key, str) else list(key)
        node = data
        for depth, part in enumerate(parts):
            if not isinstance(node, dict):
                raise MalformedInput(self.paths[name], f"{name}#{'.'.join(parts[:depth])}: expected an object, "
                                                       f"got {type(node).__name__}")
            if part not in node or node[part] is None:
                if not optional:
                    self.missing.append(f"{name}#{'.'.join(parts)}")
                return None
            node = node[part]
        return check(node, kinds, (self.paths[name], f"{name}#{'.'.join(parts)}"))

    def text(self, name):
        """The file as text, None when absent. The worker log is decoded leniently: its stage lines are ASCII."""
        if not self.paths[name].is_file():
            if name in self.expected:
                self.missing.append(name)
            return None
        return read_bytes(self.paths[name]).decode("utf-8-sig", errors="replace")

    def digest(self, name):
        if not self.paths[name].is_file():
            self.missing.append(name)
            return None
        return sha256_file(self.paths[name])

    def note_run_id(self, name, seen=None):
        """Warn when a file belongs to another run than the directory says."""
        if seen is None:
            seen = self.pick(name, "run_id", str, optional=True)
        if seen is not None and seen != self.run_dir.name:
            self.warnings.append(f"run_id in {name} is {seen}; the directory is named {self.run_dir.name}")

    def stages(self, log):
        if log is None:
            for key in ("list", "stage_sum_ok", "ok0", "parents", "tags"):
                self.set(f"stages.{key}", None, "native_worker.log")
            return
        found = parse_stages(log)
        parents = parent_stages(found)
        self.set("stages.list", [{key: stage[key] for key in ("stage", "ok", "seconds", "line")} for stage in found],
                 "native_worker.log#stage lines, line per stage")
        self.set("stages.ok0", [stage["stage"] for stage in found if not stage["ok"]],
                 "native_worker.log#stage lines logged with ok=0")
        self.set("stages.parents", [found[index]["stage"] for index in sorted(parents)],
                 "native_worker.log#stages that wrap the locate./edit_readback. stage of the same field")
        self.set("stages.tags", list(dict.fromkeys(stage["tag"] for stage in found)), "native_worker.log#tag per stage line")
        total = stage_sum_ok(found, parents)
        if total is not None:
            self.set("stages.stage_sum_ok", total,
                     "native_worker.log#seconds of the ok=1 stage lines that are not parents")

    def finish(self):
        self.data["missing"] = list(dict.fromkeys(self.missing))
        self.data["warnings"] = self.warnings
        self.data["sources"] = self.sources
        return self.data


def build_windows(run_dir, ledger, ledger_path, override):
    summary, path = summary_name(run_dir), summary_path(run_dir)
    signals = machine_signals(run_dir, None)
    machine = override or (signals[0][0] if signals else None)
    expected = set(WINDOWS_FILES) | {"guest": {summary}, "fa706g3": {EXECUTION_HOST}}.get(machine, set())
    r = Receipt(run_dir, {**{name: run_dir / name for name in (*WINDOWS_FILES, EXECUTION_HOST)}, summary: path}, expected)
    r.bind_ledger(ledger, ledger_path, run_dir.name)
    r.machine(override, signals)
    r.set("identity.run_id", run_dir.name, "directory name")

    for key in ("release_verdict", "execution_status", "mode"):
        r.set(f"verdicts.{key}", r.pick("result.json", key, str), f"result.json#{key}")
    for key in ("verified_pass", "cleanup_confirmed"):
        r.set(f"verdicts.{key}", r.pick("result.json", key, bool), f"result.json#{key}")

    started, finished = r.pick("process.json", "started_at_ns", int), r.pick("process.json", "finished_at_ns", int)
    where = "process.json#finished_at_ns - started_at_ns"
    r.set("seconds.guest", None if started is None or finished is None
          else ns_seconds(r.paths["process.json"], where, finished, started), where)
    r.note_run_id("process.json")

    action = r.pick("native_worker.json", "script_action_elapsed_ns", int)
    r.set("seconds.script_action", None if action is None else action / 10**9,
          "native_worker.json#script_action_elapsed_ns")
    r.stages(r.text("native_worker.log"))

    proof_run_id = r.pick("proof.json", "run_id", str)
    r.set("artifacts.proof_run_id", proof_run_id, "proof.json#run_id")
    r.note_run_id("proof.json", proof_run_id)
    project, gcode = r.pick("proof.json", "project_sha256", str), r.pick("proof.json", "gcode_sha256", str)
    r.set("artifacts.project_sha256", project, "proof.json#project_sha256")
    r.set("artifacts.gcode_sha256", gcode, "proof.json#gcode_sha256")
    project_now, gcode_now = r.digest(PROJECT), r.digest(GCODE)
    r.set("artifacts.project_sha256_recomputed", project_now, f"{PROJECT}#sha256")
    r.set("artifacts.gcode_sha256_recomputed", gcode_now, f"{GCODE}#sha256")
    r.set("artifacts.artifact_hashes_match", hashes_match((project, gcode), (project_now, gcode_now)),
          f"proof.json#project_sha256,gcode_sha256 compared with {PROJECT}#sha256 and {GCODE}#sha256")
    r.set("artifacts.teardown_active_processes", r.pick("teardown.json", "active_processes", int),
          "teardown.json#active_processes")
    r.note_run_id("teardown.json")

    if machine == "fa706g3" or (run_dir / EXECUTION_HOST).is_file():
        if r.document(EXECUTION_HOST) is None:
            r.set("identity.execution_host", None, EXECUTION_HOST)
        else:
            for key, kind in (("hyper_v_guest", bool), ("machine", str), ("flag", str)):
                r.set(f"identity.execution_host.{key}", r.pick(EXECUTION_HOST, key, kind), f"{EXECUTION_HOST}#{key}")

    if machine == "guest" or path.is_file():
        if r.document(summary) is None:
            r.set("verdicts.comparison", None, f"{summary}#comparison")
        else:
            r.note_run_id(summary)
            comparison = r.pick(summary, "comparison", dict)
            if comparison is None:
                r.set("verdicts.comparison", None, f"{summary}#comparison")
            else:
                for key, kinds, optional in (("status", (str,), False), ("business_status", (str,), False),
                                             ("unmet_expectations", (list,), True), ("reason", (str,), True)):
                    value = r.pick(summary, f"comparison.{key}", *kinds, optional=optional)
                    if key == "unmet_expectations" and value is not None:
                        value = strings(value, (path, f"{summary}#comparison.unmet_expectations"))
                    r.set(f"verdicts.comparison.{key}", value, f"{summary}#comparison.{key}")
            for key, field in (("host_wall_seconds", "host_wall"), ("harvest_seconds", "harvest")):
                r.set(f"seconds.{field}", r.pick(summary, key, int, float), f"{summary}#{key}")

    scenario, origin = first_of((lambda: (r.pick(summary, "scenario", str), f"{summary}#scenario"),
                                 lambda: (r.pick("native_worker.json", "scenario", str), "native_worker.json#scenario"),
                                 lambda: r.ledger_text("scenario")))
    r.set("identity.scenario", scenario, origin)
    commit, origin = first_of((lambda: (r.pick(summary, "source_sha", str), f"{summary}#source_sha"),
                               lambda: r.ledger_text("commit")))
    r.set("identity.source_commit", commit, origin)
    r.set("identity.label", *r.ledger_text("label"))
    return r.finish()


def build_mac(run_dir, name, data, ledger, ledger_path, override):
    signals = machine_signals(run_dir, name)
    r = Receipt(run_dir, {name: run_dir / name}, {name})
    r.docs[name] = data
    run_id = check(data.get("run_id"), (str,), (r.paths[name], f"{name}#run_id"))
    if not run_id.strip():
        raise MalformedInput(r.paths[name], f"{name}#run_id: blank")
    r.bind_ledger(ledger, ledger_path, run_id)
    r.machine(override, signals)
    r.set("identity.run_id", run_id, f"{name}#run_id")
    if HARVEST_RUN_ID.fullmatch(run_dir.name) and run_dir.name != run_id:
        r.warnings.append(f"the directory is named {run_dir.name}; run_id in {name} is {run_id}")
    goal = r.pick(name, "goal", str)
    r.set("identity.goal", goal if goal and goal.strip() else None, f"{name}#goal")
    r.set("verdicts.verdict", r.pick(name, "verdict", str), f"{name}#verdict")
    r.set("verdicts.failure_stage", r.pick(name, "failure_stage", str, optional=True), f"{name}#failure_stage")
    error = r.pick(name, "error", str, optional=True)
    r.set("verdicts.error", None if error is None else error[:MAC_ERROR_LIMIT], f"{name}#error")
    started, finished = r.pick(name, "started_at", str), r.pick(name, "finished_at", str)
    where = f"{name}#finished_at - started_at"
    r.set("seconds.mac_wall", None if started is None or finished is None
          else iso_seconds(r.paths[name], where, finished, started), where)
    phases = r.pick(name, "guest.phases", dict)
    r.set("verdicts.guest_phases", None if phases is None else {}, f"{name}#guest.phases")
    for phase, row in (phases or {}).items():
        check(row, (dict,), (r.paths[name], f"{name}#guest.phases.{phase}"))
        for key, kinds in (("pid", (int,)), ("layers", (list,)), ("wall", (str,))):
            value = r.pick(name, ("guest", "phases", phase, key), *kinds)
            if key == "layers" and value is not None:
                value = strings(value, (r.paths[name], f"{name}#guest.phases.{phase}.layers"))
            r.set(("verdicts", "guest_phases", phase, key), value, f"{name}#guest.phases.{phase}.{key}")
    echo = r.pick(name, "wall_loops_gcode_echo", list, optional=True)
    if echo is not None:
        echo = strings(echo, (r.paths[name], f"{name}#wall_loops_gcode_echo"))
    r.set("verdicts.wall_loops_gcode_echo", echo, f"{name}#wall_loops_gcode_echo")
    scenario, origin = r.ledger_text("scenario")
    r.set("identity.scenario", scenario, origin)
    commit, origin = r.ledger_text("commit")
    r.set("identity.source_commit", commit, origin)
    r.set("identity.label", *r.ledger_text("label"))
    return r.finish()


def mac_results(run_dir):
    """[(file name, result)] of every Mac runner result in the directory."""
    names = ["result.json"] + sorted(path.name for path in run_dir.glob("*_result.json"))
    found = []
    for name in dict.fromkeys(names):
        if (run_dir / name).is_file():
            data = parse_json(run_dir / name)
            if is_mac_result(data):
                found.append((name, data))
    return found


def receipts_for(run_dir, ledger=None, ledger_path=None, machine=None) -> list:
    """One receipt per run in `run_dir` (several for a Mac evidence directory).

    `ledger` is what load_ledger returned, `ledger_path` how the operator named it, `machine` the --machine choice."""
    run_dir = Path(run_dir)
    macs = mac_results(run_dir)
    if macs:
        return [build_mac(run_dir, name, data, ledger, ledger_path, machine) for name, data in macs]
    return [build_windows(run_dir, ledger, ledger_path, machine)]


def shown(value):
    """A table cell: '-' for what is not available, seconds to 3 decimals."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|")


def markdown(receipts) -> str:
    """The table: one row per receipt, in the order given."""
    rows = []
    for receipt in receipts:
        identity, verdicts, seconds, stages = (receipt[name] for name in ("identity", "verdicts", "seconds", "stages"))
        comparison = verdicts["comparison"] or {}
        failed = None if stages["ok0"] is None else "; ".join(stages["ok0"]) or "none"
        rows.append([identity["machine"], identity["label"], identity["scenario"] or identity["goal"],
                     identity["run_id"][:8],
                     None if identity["source_commit"] is None else identity["source_commit"][:7],
                     verdicts["release_verdict"] or verdicts["verdict"], verdicts["verified_pass"],
                     "/".join(part for part in (comparison.get("status"), comparison.get("business_status"))
                              if part) or None,
                     verdicts["cleanup_confirmed"], seconds["guest"],
                     seconds["host_wall"] if seconds["host_wall"] is not None else seconds["mac_wall"],
                     seconds["script_action"], stages["stage_sum_ok"], failed])
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(shown(value) for value in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def notes(receipts):
    for receipt in receipts:
        short = receipt["identity"]["run_id"][:8]
        if receipt["artifacts"]["artifact_hashes_match"] is False:
            yield f"{short}: artifact_hashes_match=false"
        if receipt["missing"]:
            yield f"{short}: missing {', '.join(receipt['missing'])}"
        for warning in receipt["warnings"]:
            yield f"{short}: {warning}"


def split_runs(text):
    runs = [part.strip() for part in text.split(",")]
    for run_id in runs:
        if not NAME.fullmatch(run_id):
            raise ReceiptError("--runs", f"{run_id!r} is not a run id")
    return runs


def discover(paths, runs) -> list:
    """The run directories to read: <root>/<id> under every root for --runs, else each directory itself."""
    found = []
    for root in paths:
        if not root.is_dir():
            raise ReceiptError(root, "not a directory")
        if runs:
            found += [root / run_id for run_id in runs if (root / run_id).is_dir()]
            continue
        if mac_results(root) or any((root / name).is_file() for name in (*WINDOWS_FILES, EXECUTION_HOST, "native_run.log")):
            found.append(root)
            continue
        try:
            count = sum(1 for path in root.iterdir() if HARVEST_RUN_ID.fullmatch(path.name) and path.is_dir())
        except OSError as error:
            raise ReceiptError(root, f"cannot list it ({error.strerror or error})") from None
        if count:
            raise ReceiptError(root, f"is a harvest root with {count} run directories; "
                                     "pass --runs <id,id,...> or pass run directories directly")
        found.append(root)      # an empty run directory is a harvest that reached nothing: still one receipt
    if runs:
        lost = [run_id for run_id in runs if not any((root / run_id).is_dir() for root in paths)]
        if lost:
            raise ReceiptError(", ".join(map(str, paths)), "run directory not found: " + ", ".join(lost))
    return found


def check_output_dir(out_dir, inputs):
    """Receipts are never written into a harvest."""
    out = out_dir.resolve()
    for path in inputs:
        if out == path.resolve() or path.resolve() in out.parents:
            raise WriteFailed(out_dir, f"is inside the harvest {path}; receipts are written outside it")


def write_receipts(receipts, out_dir):
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WriteFailed(out_dir, f"cannot create it ({error.strerror or error})") from None
    for receipt in receipts:
        run_id = receipt["identity"]["run_id"]
        if not NAME.fullmatch(run_id):
            raise WriteFailed(out_dir, f"run id {run_id!r} is not usable as a file name")
        target, pending = out_dir / f"{run_id}.json", out_dir / f"{run_id}.json.tmp"
        try:
            pending.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(pending, target)       # a re-run refreshes a receipt; a reader never sees a half file
        except OSError as error:
            raise WriteFailed(target, f"cannot write it ({error.strerror or error})") from None


def main(argv=None) -> int:
    """CLI entry point: 0 when every receipt was produced, 2 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path, metavar="harvest_root_or_run_dir")
    parser.add_argument("--runs", metavar="id,id,...", help="run ids to read under each harvest root")
    parser.add_argument("--ledger", type=Path, metavar="path", help="session ledger: JSON Lines, one run per line")
    parser.add_argument("--machine", choices=MACHINES, help="replace the machine inferred from the files")
    parser.add_argument("--json", dest="json_dir", type=Path, metavar="out_dir",
                        help="also write <run_id>.json per run into this directory")
    args = parser.parse_args(argv)
    try:
        targets = discover(args.paths, split_runs(args.runs) if args.runs is not None else None)
    except ReceiptError as error:
        print(f"ninehour_receipts: {error}", file=sys.stderr)
        return 2
    failures, built, seen = [], [], set()
    ledger, ledger_path = None, None
    if args.ledger is not None:
        ledger_path = str(args.ledger)
        try:
            ledger = load_ledger(args.ledger)
        except ReceiptError as error:
            failures.append(error)
    for run_dir in targets:
        try:
            for receipt in receipts_for(run_dir, ledger, ledger_path, args.machine):
                run_id = receipt["identity"]["run_id"]
                if run_id in seen:
                    raise MalformedInput(run_dir, f"run {run_id} appears more than once; there is one receipt per run")
                seen.add(run_id)
                built.append(receipt)
        except ReceiptError as error:
            failures.append(error)
    print(markdown(built), end="")      # stdout carries the table and nothing else
    if args.json_dir is not None:
        try:
            check_output_dir(args.json_dir, args.paths)
            if built:
                write_receipts(built, args.json_dir)
                print(f"ninehour_receipts: wrote {len(built)} receipt(s) to {args.json_dir}", file=sys.stderr)
        except ReceiptError as error:
            failures.append(error)
    for failure in failures:
        print(f"ninehour_receipts: {failure}", file=sys.stderr)
    for note in notes(built):
        print(f"ninehour_receipts: {note}", file=sys.stderr)
    print(f"ninehour_receipts: {len(built)} receipt(s); the table rounds seconds to 3 decimals and shows 7 characters "
          "of the commit - exact values, and the file behind every field, are in the JSON receipts; "
          "'-' = not available; a Mac row shows its Mac wall under 'host s'", file=sys.stderr)
    return 2 if failures else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
