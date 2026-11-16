"""Strict run-scoped mailbox data. This internal transport is not MCP HTTP."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

MAX_CALLS = 12
MAX_CLICKS = 6
MAX_RUNTIME_S = 900


class ProtocolError(ValueError):
    pass


def valid_run_id(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ProtocolError("invalid_run_id")
    return value


def read_json(path: Path):
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ProtocolError("request_too_large")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("duplicate_field")
            result[key] = value
        return result
    def nonfinite(_value):
        raise ProtocolError("nonfinite_number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProtocolError("invalid_json") from exc


def check_cancel(artifact_dir: Path, run_id: str) -> None:
    """Host-only control file; malformed requests stop the worker as well."""
    path = artifact_dir / "control_cancel.json"
    if not path.exists():
        return
    value = read_json(path)
    if (type(value) is not dict or set(value) != {"schema_version", "run_id", "reason"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["run_id"]) is not str or value["run_id"] != run_id
            or value["reason"] != "host_stopped"):
        raise ProtocolError("invalid_cancel")
    raise ProtocolError("host_cancelled")


def validate_request(value, *, run_id: str, expected_seq: int, observation_id: str | None):
    if (type(value) is not dict or set(value) != {
            "schema_version", "run_id", "seq", "method", "arguments", "observation_id"}):
        raise ProtocolError("invalid_fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ProtocolError("invalid_version")
    if value["run_id"] != run_id or type(value["run_id"]) is not str:
        raise ProtocolError("wrong_run")
    if type(value["seq"]) is not int or value["seq"] != expected_seq or not 1 <= expected_seq <= MAX_CALLS:
        raise ProtocolError("invalid_sequence")
    method, arguments = value["method"], value["arguments"]
    if type(method) is not str or method not in {"observe", "click", "finish"}:
        raise ProtocolError("unknown_tool")
    if value["observation_id"] != observation_id or type(value["observation_id"]) not in (str, type(None)):
        raise ProtocolError("stale_observation")
    if expected_seq == 1 and method != "observe":
        raise ProtocolError("observe_first")
    if type(arguments) is not dict:
        raise ProtocolError("invalid_arguments")
    if method == "click":
        if (set(arguments) != {"x", "y"} or observation_id is None
                or type(arguments["x"]) is not int or type(arguments["y"]) is not int
                or not 40 <= arguments["x"] <= 312 or not 31 <= arguments["y"] <= 67):
            raise ProtocolError("click_outside_tab_scope")
    elif arguments:
        raise ProtocolError("invalid_arguments")
    return {**value, "arguments": dict(arguments)}


def write_json_once(path: Path, value):
    """Publish a complete file atomically without replacing any prior record."""
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # Windows rename is non-replacing; this worker is guest-only.
        if os.name != "nt":
            os.link(temporary, path)
            temporary.unlink()
        else:
            temporary.rename(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
