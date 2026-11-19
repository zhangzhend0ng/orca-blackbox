"""Compose two admitted cube operations from independently accepted recordings."""
from dataclasses import asdict, dataclass
from itertools import combinations
import hashlib

from .agent_protocol import LAYER_FIXTURE_SHA256, ProtocolError
from .native_config_cases import CATALOG_PATH, DOMAIN, generate


@dataclass(frozen=True)
class Operation:
    recording: str
    start: int
    stop: int
    requires: frozenset[str]
    removes: frozenset[str]
    ensures: frozenset[str]
    settings: tuple[tuple[str, str], ...] = ()
    translation_x_mm: int = 0
    readback: str = ""


INITIAL = frozenset({"quality_basic", "x_original", "layer_0.40", "seam_aligned", "ironing_off"})
RECORDING_DIGESTS = {
    "uia_replay_layer": "d244d3335578d3a853019e58f40f0ec25c0f436c165fb9fb4781d4388fcd2b46",
    "uia_replay_move_layer": "fa651f587b7792e8c7e7d368115df9a51c1579bc33ef14c5e588a65aaf78209c",
    "uia_replay_enums": "95213fa398a140bcc96018b14c613f70a0d49b77edd60fce55635e9620033481",
}
OPERATIONS = {
    "layer": Operation("uia_replay_layer", 0, 3, frozenset({"quality_basic", "layer_0.40"}),
                       frozenset({"layer_0.40"}), frozenset({"layer_0.24"}), (("layer_height", "0.24"),)),
    "move": Operation("uia_replay_move_layer", 4, 13, frozenset({"x_original"}),
                      frozenset({"x_original"}), frozenset({"x_plus_10"}), translation_x_mm=10),
    "seam": Operation("uia_replay_enums", 0, 6, frozenset({"quality_basic", "seam_aligned"}),
                      frozenset({"seam_aligned"}), frozenset({"seam_random"}),
                      (("seam_position", "random"),), readback="Random"),
    "ironing": Operation("uia_replay_enums", 6, 18, frozenset({"quality_basic", "ironing_off"}),
                         frozenset({"quality_basic", "ironing_off"}), frozenset({"quality_advanced", "ironing_topmost"}),
                         (("ironing_type", "topmost"),), readback="Topmost surface"),
}


def admitted(order):
    state = INITIAL
    for name in order:
        op = OPERATIONS[name]
        if not op.requires <= state:
            return False
        state = (state - op.removes) | op.ensures
    return True


def generate_cases():
    cases = {}
    for first, second in combinations(OPERATIONS, 2):
        orders = [(first, second), (second, first)]
        legal = [order for order in orders if admitted(order)]
        selected = legal if {first, second} == {"layer", "move"} else legal[:1]
        for order in selected:
            cases["pair_" + "_".join(order)] = order
    return cases


LEGACY_PAIRS = generate_cases()
CONFIG_PLAN = generate(admitted)
CONFIG_CASES = {row["id"]: row for rows in (CONFIG_PLAN["legal"], CONFIG_PLAN["dependency"])
                for row in rows if row["selection"] == "selected"}
PAIR_CASES = {**LEGACY_PAIRS, **{name: row["order"] for name, row in CONFIG_CASES.items()}}
PAIR_ENUM_CASES = (frozenset(s for s, order in PAIR_CASES.items() if {"seam", "ironing"}.intersection(order))
                   | CONFIG_CASES.keys())
PAIR_MOVE_CASES = frozenset(s for s, order in PAIR_CASES.items() if "move" in order)


def enum_values(scenario):
    return frozenset(OPERATIONS[name].readback for name in PAIR_CASES[scenario] if OPERATIONS[name].readback)


def expected_settings(scenario):
    return dict(setting for name in PAIR_CASES[scenario] for setting in OPERATIONS[name].settings)


def compile_pair(scenario):
    from .native_uia_replay import read_recipe, verify_visual_steps

    def pinned_recording(name):
        source, digest = read_recipe(name)
        if digest != RECORDING_DIGESTS[name]:
            raise ValueError("pair_recording_digest_changed:" + name)
        return source, digest

    steps, segments = [], []
    order = PAIR_CASES[scenario]
    case = CONFIG_CASES.get(scenario)
    checkpoints = {}
    if case:
        layer, _ = pinned_recording("uia_replay_layer")
        steps.append({"tool": "Snapshot", "arguments": {}})
        checkpoints[1] = {"visible": False, "seam": "Aligned", "layer": layer["steps"][1]["arguments"]["target"]}
        if case.get("kind") == "mode_cycle":
            source, _ = pinned_recording(OPERATIONS["ironing"].recording)
            advanced = source["steps"][OPERATIONS["ironing"].start]
            for visible in (True, False, True):
                steps.extend([advanced, {"tool": "Snapshot", "arguments": {}}])
                checkpoints[len(steps)] = {"visible": visible}
    for name in order:
        op = OPERATIONS[name]
        source, digest = pinned_recording(op.recording)
        fragment = source["steps"][op.start:op.stop]
        if len(fragment) != op.stop - op.start or any(step["tool"] == "Shortcut" for step in fragment):
            raise ValueError("pair_recording_boundary")
        first = len(steps) + 1
        if fragment[0]["tool"] != "Snapshot":
            steps.append({"tool": "Snapshot", "arguments": {}})
        steps.extend(fragment)
        contract = asdict(op)
        for key in ("requires", "removes", "ensures"):
            contract[key] = sorted(contract[key])
        segments.append({"operation": name, "first": first, "last": len(steps),
                         "recording_sha256": digest, "source": source["source"], **contract})
    save, digest = pinned_recording("uia_replay_move_layer")
    steps.extend(save["steps"][-5:])
    verify_visual_steps(steps, scenario)
    recipe = {"scenario": scenario, "initial_tab": "Quality", "fixture_sha256": LAYER_FIXTURE_SHA256,
            "initial_state": sorted(INITIAL), "segments": segments, "save_recording_sha256": digest,
            "steps": steps}
    if case:
        recipe.update(config_case=case, checkpoints=checkpoints,
                      catalog_sha256=hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest())
    return recipe


def check_config_snapshot(checkpoint, observation, *, live):
    groups = observation.get("process_groups", ())
    if "Seam" not in groups or ("Ironing" in groups) != checkpoint["visible"]:
        raise ProtocolError("config_ironing_visibility")
    if "seam" in checkpoint and checkpoint["seam"] not in observation.get("process_values", ()):
        raise ProtocolError("config_initial_seam")
    if live and "layer" in checkpoint:
        values = [item.get("value") for item in observation["controls"] if item["target"] == checkpoint["layer"]]
        if values not in (["0.4"], ["0.40"]):
            raise ProtocolError("config_initial_layer")


def check_live(segment, seq, observations, steps):
    if not observations or "controls" not in observations:
        raise ProtocolError("pair_owned_main_missing")
    name = segment["operation"]
    if seq == segment["first"]:
        if name in {"layer", "seam", "ironing"} and "Ironing" in observations.get("process_groups", ()):
            raise ProtocolError("pair_quality_basic_precondition")
        if name == "seam" and "Aligned" not in observations.get("process_values", ()):
            raise ProtocolError("pair_seam_aligned_precondition")
    if name == "layer":
        target = steps[segment["first"]]["arguments"]["target"]
        values = [item.get("value") for item in observations["controls"] if item["target"] == target]
        expected = ("0.4", "0.40") if seq == segment["first"] else ("0.24",)
        if len(values) != 1 or values[0] not in expected:
            raise ProtocolError("pair_layer_initial_or_readback")


def verify_pair(scenario, project, fixture, gcode, *, cancelled):
    from .agent_layer_verify import analyze_gcode
    from .agent_verify import _require
    from .pilot_common import inspect_preserved_settings, require_gcode_settings
    from .pilot_transform import verify_translation
    from .project_3mf import _archive, inspect_project
    from .script_verify import _json

    _require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "pair_fixture")
    order = PAIR_CASES[scenario]
    settings = expected_settings(scenario)
    layer = settings.get("layer_height", "0.4")
    if "move" in order:
        info = verify_translation(project, fixture, gcode, axis="x", distance=OPERATIONS["move"].translation_x_mm,
                                  cancelled=cancelled, layer_edit="layer" in order, pair_settings=settings)
    else:
        config = "Metadata/project_settings.config"
        inspect_preserved_settings(_json(_archive(project, cancelled)[config]), _json(_archive(fixture, cancelled)[config]),
                                   allowed_changes=settings, cancelled=cancelled)
        case = CONFIG_CASES.get(scenario)
        gcode_settings = settings
        if case:
            baseline = _json(_archive(fixture, cancelled)[config])
            _require(all(settings.get(key, baseline.get(key)) == value for key, value in case["values"].items()),
                     "config_value_plan_mismatch")
            gcode_settings = {**case["values"], **{key: baseline[key] for key in DOMAIN["preserve"]},
                              "initial_layer_print_height": DOMAIN["fixed"]["initial_layer_print_height"]}
        require_gcode_settings(gcode, gcode_settings, "pair_gcode_settings")
        gcode_info = analyze_gcode(gcode, layer_height=layer, cancelled=cancelled, inspect_ironing=case is not None)
        _require(gcode_info["layer_count"] == (112 if "layer" in order else 68)
                 and gcode_info["object_tools"] == [0], "pair_gcode_layer_or_tool")
        info = {"project": inspect_project(project, fixture, layer_height=layer, cancelled=cancelled),
                "gcode": gcode_info}
        if case:
            expected_z = [gcode_info["last_z"]] if case["values"]["ironing_type"] == "topmost" else []
            _require(gcode_info["ironing_z"] == expected_z, "config_actual_ironing_layers")
            info["verified_gcode_settings"] = gcode_settings
            info["config_case"] = case
    return dict(info, order=order, verified_settings=settings)
