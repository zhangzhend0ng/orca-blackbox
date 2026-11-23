"""Strict run-scoped mailbox data. This internal transport is not MCP HTTP."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
import re

MAX_CALLS = 12
MAX_CLICKS = 6
MAX_RUNTIME_S = 900
LAYER_CASE = "m3d_param_reslice"
PROJECT_CASE = "m3g_export_3mf"
LAYER_FIXTURE = "fixtures/agent_layer_cube.3mf"
LAYER_FIXTURE_SHA256 = "ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef"
# The Feishu process cases' precondition ("U1 0.4mm喷嘴、PLA耗材和0.20mm标准工艺预设"):
# the same cube on the U1 0.4 nozzle, 0.20mm Standard, PLA. Built and pinned by
# tools/build_feishu_std_fixture.py; nothing else may write it.
STD_FIXTURE = "fixtures/feishu_std_cube.3mf"
STD_FIXTURE_SHA256 = "0690071f9501bac804d17c025015f2fe2bed4ce48b90e2f28946e307c56c1a0b"
# A scenario named `<base>_std02` is `<base>` on STD_FIXTURE: the same tab spec, ops,
# pilot and dispatch, another fixture (native_pilots.native_fixture). The full name
# stays in scope.json and the report, so those runs keep apart from the cube's.
STD_SUFFIX = "_std02"
# The save-only baseline on that fixture - a scenario of its own, not a `_std02` twin.
STD_SCENARIO = "uia_param_std_save_only"
# The filament-choice popups paint "<n> <filament type>": Default / 1 PETG / 2 PLA /
# 3 PLA / 4 PLA / 5 PLA on the cube (census 67690ed4 / c814315c, the 'Support/raft
# base' popup in tools/param_ui_popups_2.4.0.json). 'PETG' names the cube's extruder 1;
# every filament of STD_FIXTURE is PLA, so the same extruder is the row "1 PLA" there.
# A preset name matches no row (the rows carry the type, not the preset), and 'PLA'
# alone is every row: the first one the OCR reads would be clicked.
STD_TARGETS = {"PETG": "1 PLA"}
# The Feishu rows also name their model (圆柱体 / 小船 / 欧特克 FDM 测试 / 立方体复制成 2
# 个 ...), and a single cube cannot show support, a bridge, an arc or a tool change: the
# five support-family cases' G-codes hold no Support block (2026-11-24,
# docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24). This plate carries those
# features - 立方体, 圆柱体, 搭桥, 悬垂台阶 and a second 立方体 on extruder 3 - on the
# cube's own slicer settings (tools/build_shapes_fixture.py; not yet rebuilt on the
# precondition settings). Pin: the builder asserts the file it writes has this hash.
SHAPES_FIXTURE = "fixtures/feishu_shapes_plate.3mf"
SHAPES_FIXTURE_SHA256 = "ee0a22ea21f86f1ba76838fd06fc093b026a7cf7942074c601d0ad4e648e16f9"
SHAPES_SUFFIX = "_shapes"
SHAPES_SCENARIO = "uia_param_shapes_save_only"
# suffix -> the fixture a `<base><suffix>` scenario opens
FIXTURE_SUFFIXES = {STD_SUFFIX: (STD_FIXTURE, STD_FIXTURE_SHA256),
                    SHAPES_SUFFIX: (SHAPES_FIXTURE, SHAPES_FIXTURE_SHA256)}
# suffix -> the rowcombo targets that name a filament row differently on that fixture
# (the shapes plate keeps the cube's filaments, so nothing is substituted there)
SUFFIX_TARGETS = {STD_SUFFIX: STD_TARGETS}


def base_scenario(name):
    """The scenario a suffixed name runs as: the name without its fixture suffix."""
    if type(name) is str:
        for suffix in sorted(FIXTURE_SUFFIXES, key=len, reverse=True):
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[:-len(suffix)]
    return name


def fixture_suffix(name):
    """The fixture suffix `name` carries ("" when it opens the cube)."""
    if type(name) is not str:
        return ""
    return name[len(base_scenario(name)):]


def suffixed_fixture(scenario):
    """(fixture, sha256) of a scenario that opens another project than the cube's -
    a suffixed name or one of the save-only baselines - else None."""
    if scenario in (STD_SCENARIO, SHAPES_SCENARIO):
        return FIXTURE_SUFFIXES[STD_SUFFIX if scenario == STD_SCENARIO else SHAPES_SUFFIX]
    return FIXTURE_SUFFIXES.get(fixture_suffix(scenario))


def agent_profile(case_id: str) -> dict:
    """Code-owned capabilities; never derive authority from model text."""
    profiles = {
        "m1_minimal_loop": ("ai-tabs-1", ("observe", "click", "finish")),
        LAYER_CASE: ("ai-layer-1", ("observe", "click", "edit", "slice", "export_gcode", "finish")),
        PROJECT_CASE: ("ai-project-1", ("observe", "click", "edit", "save_project",
                                      "reopen_project", "slice", "export_gcode", "finish")),
    }
    if type(case_id) is not str or case_id not in profiles:
        raise ProtocolError("unknown_case")
    version, tools = profiles[case_id]
    return {"contract_version": version, "tools": tools}


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


def validate_request(value, *, run_id: str, expected_seq: int, observation_id: str | None,
                     case_id: str = "m1_minimal_loop"):
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
    if type(method) is not str or method not in agent_profile(case_id)["tools"]:
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
    elif method == "edit":
        if (set(arguments) != {"x", "y", "text"} or observation_id is None
                or type(arguments["x"]) is not int or type(arguments["y"]) is not int
                or not 0 <= arguments["x"] < 4096 or not 0 <= arguments["y"] < 2160
                or type(arguments["text"]) is not str
                or re.fullmatch(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?", arguments["text"]) is None):
            raise ProtocolError("invalid_numeric_edit")
        if not Decimal("0.16") <= Decimal(arguments["text"]) <= Decimal("0.56"):
            raise ProtocolError("numeric_edit_out_of_range")
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
