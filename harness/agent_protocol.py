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
# How long the engine waits for the exported G-code to appear and stop changing.
# 60 s was enough for the 27 mm cube (the file is there in about two seconds); the
# Feishu rows' own models on the model fixtures (a 3DBenchy of 225,000 triangles,
# a 118 mm bunny) slice longer, and a wait that is too short reads as a failed
# case although nothing is wrong with it (2026-11-24).
EXPORT_STABLE_WAIT_S = 180
LAYER_FIXTURE_SHA256 = "ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef"
# The Feishu process cases' precondition ("U1 0.4mm喷嘴、PLA耗材和0.20mm标准工艺预设"):
# the same cube on the U1 0.4 nozzle, 0.20mm Standard, PLA. Built and pinned by
# tools/build_feishu_std_fixture.py; nothing else may write it.
STD_FIXTURE = "fixtures/feishu_std_cube.3mf"
STD_FIXTURE_SHA256 = "36389ec3d26c54fc8d3e6bfccac3097fb080a12ab8fab0f2b7f8038cfc278d94"
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
# The rows' own models on the precondition settings (tools/build_model_fixtures.py,
# 2026-11-24): the meshes are the slicer's built-in "add model" files
# (resources/handy_models) or generated primitives; the project settings are
# STD_FIXTURE's byte for byte, so the app keeps them as it keeps the cube's.
#   suffix -> (file under fixtures/, sha256, key of the baseline scenario)
# The hashes were read off the builder's output and re-checked on a rebuild that
# rewrote nothing; tools/test_param_engine_sim.py checks the bytes against them.
MODEL_FIXTURES = {
    "_boat": ("feishu_std_boat.3mf",
              "d550f8ac10adfbea6fcfc61be46d76f07515384e20225d425e42eb49d50b4d65", "boat"),
    "_boat2": ("feishu_std_boat2.3mf",
               "e2e5bfa332259810823dee58953f9af5b617883772b146784bb061b0251a21fc", "boat2"),
    "_fdmt": ("feishu_std_fdmt.3mf",
              "02b5d2f3ed8addad78be88e5a5fa177c8b8df187dad2344d97b9da36912af92b", "fdmt"),
    "_fdmt2": ("feishu_std_fdmt2.3mf",
               "57a55b062107ba3dc4f46d4026c6bf9e0a5341caa1e9294fb9de57a0b6d13f60", "fdmt2"),
    "_cubes2": ("feishu_std_cubes2.3mf",
                "2ff94a1efffe621b3a2c5358b61e65aad1d228b3ba5525d3daf6651a40b7ec21", "cubes2"),
    "_sphere": ("feishu_std_sphere.3mf",
                "f5f83d00545522c7cde44c0cd4260c325418707afdc83e6056390a0b8800d13c", "sphere"),
    "_cyl": ("feishu_std_cylinder.3mf",
             "f710bffe6a13cd86ab57cf6ed288e372fcb41c89c66d8c3ce0eeeee6fb9fe43b", "cyl"),
    "_bunny": ("feishu_std_bunny.3mf",
               "bb3609710d30e1ea9ba08a9b2937a6e0692effda1213bd56256be8c2e4dc5489", "bunny"),
    "_hell": ("feishu_std_hell.3mf",
              "b69b63df1973afad4155c89f953a799783b91c53840f77d8915cdf1825dd30ca", "hell"),
}
FIXTURE_SUFFIXES.update({suffix: ("fixtures/" + file, sha)
                         for suffix, (file, sha, _key) in MODEL_FIXTURES.items()})
# suffix -> (its save-only baseline, the baseline's case id). A baseline is a
# scenario of its own, not a twin: nothing is edited, the run shows what the app
# does with the fixture as it is.
BASELINES = {STD_SUFFIX: (STD_SCENARIO, "param_std_save_only"),
             SHAPES_SUFFIX: (SHAPES_SCENARIO, "param_shapes_save_only")}
BASELINES.update({suffix: ("uia_param_%s_save_only" % key, "param_%s_save_only" % key)
                  for suffix, (_file, _sha, key) in MODEL_FIXTURES.items()})
# suffix -> the rowcombo targets that name a filament row differently on that fixture
# (the shapes plate keeps the cube's filaments, so nothing is substituted there; every
# model fixture is all PLA, like the precondition cube)
SUFFIX_TARGETS = {STD_SUFFIX: STD_TARGETS}
SUFFIX_TARGETS.update({suffix: STD_TARGETS for suffix in MODEL_FIXTURES})


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
    for suffix, (baseline, _case) in BASELINES.items():
        if scenario == baseline:
            return FIXTURE_SUFFIXES[suffix]
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
