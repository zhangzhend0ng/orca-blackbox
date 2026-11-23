"""Build fixtures/feishu_std_cube.3mf from fixtures/agent_layer_cube.3mf.

The Feishu 常用工艺参数 cases state one precondition - "U1 0.4mm喷嘴、PLA耗材和
0.20mm标准工艺预设" - and take their feed numbers from it. The cube fixture is the
same 27 mm model on the U1 with 0.8 mm nozzles, a 0.40 mm layer and PETG / PLA Silk,
where filament_max_volumetric_speed 10 mm3/s over a 0.82 x 0.4 mm line caps every
extruding move at 30.5 mm/s (tools/gcode_feature_speeds.py), so the cases' feeds
above ~30 mm/s cannot be observed on it. This derives a second fixture: the same
archive members and the same model, with the config ported from the 0.8 chain to
the 0.4 chain of the vendor tree.

    python -B tools/build_feishu_std_fixture.py                   # build, print the report (JSON)
    python -B tools/build_feishu_std_fixture.py --print-sha256    # the hash only, writes nothing

How the config is ported (it starts as the cube's config):
  - a key both chains define and whose chain values differ takes the 0.4 value;
  - a key the cube customised against its own chain is overridden as well, and listed
    (overrode_customised);
  - the preset ids and every key the chosen PLA presets define follow the chosen
    presets;
  - every other key keeps the cube's value; no key is added or removed;
  - different_settings_to_system is the manifest the app itself writes for this
    project (measured, see APP_MANIFEST); where the config differs from the 0.4
    presets of the host's 2.4.1 tree is reported, not written into the fixture.

The flattener is validated before any of that: the cube's chain read through
`inherits` has to reproduce the cube's config key by key, and the leaf presets
read alone must not (the red proof).

The output's sha256 is pinned in harness/agent_protocol.py (STD_FIXTURE_SHA256).
The bytes are compared with the pin BEFORE anything is written, so a build whose
zlib deflates differently can never replace the pinned file.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from harness import agent_protocol  # noqa: E402
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256  # noqa: E402

OUTPUT = "fixtures/feishu_std_cube.3mf"
CONFIG = "Metadata/project_settings.config"
MEMBERS = ["[Content_Types].xml", "Metadata/plate_1.png", "Metadata/plate_1_small.png",
           "Metadata/plate_no_light_1.png", "Metadata/top_1.png", "Metadata/pick_1.png",
           "3D/3dmodel.model", "3D/_rels/3dmodel.model.rels", "3D/Objects/立方体_1.model",
           "Metadata/project_settings.config", "Metadata/model_settings.config",
           "Metadata/slice_info.config", "_rels/.rels"]
# The vendor tree of the slicer source (read-only).
PROFILES = Path(r"C:\coil\Projects\SnapmakerOrca\resources\profiles")
VENDOR = "Snapmaker"
# Keys of a preset file that describe the preset, not a setting.
PRESET_META = frozenset({"name", "inherits", "instantiation", "type", "setting_id", "renamed_from",
                         "description"})
# The project key the slicer keeps the print preset's compatible_printers under
# (PresetBundle::full_fff_config writes it, load_config_file reads it back).
COMPATIBLE_ALIAS = {"compatible_printers": "print_compatible_printers"}
CUBE_PRINTER = "Snapmaker U1 (0.8 nozzle)"
CUBE_PROCESS = "0.40mm Standard @Snapmaker U1 (0.8 nozzle)"
STD_PRINTER = "Snapmaker U1 (0.4 nozzle)"
STD_PROCESS = "0.20mm Standard @Snapmaker U1 (0.4 nozzle)"
# F1 is the counterpart of the cube's F1 (the support / raft filament), F2-F5 of its F2-F5.
STD_F1 = "Generic PLA @U1 0.4 nozzle"
STD_F2 = "Snapmaker PLA Basic @U1 0.4 nozzle"
WHY_F1 = ("the Generic family's unqualified PLA: it inherits fdm_filament_pla_category through "
          "Generic PLA @U1 base, the plain PLA category, not silk / high speed / CF; filament_type PLA")
WHY_F2 = ("the Snapmaker PLA with no finish or speed qualifier in its name (the other plain-category "
          "Snapmaker PLAs are Full Spectrum, Gradient, Rainbow, Marble, Starlight, Wood, Translucent, "
          "Glow, Eco; Silk / Matte / SnapSpeed / CF inherit other categories); it inherits "
          "fdm_filament_pla_category through Snapmaker PLA Basic @U1 base; instantiated for the U1 "
          "0.4 nozzle; filament_type PLA")
# Project keys the slicer fills from the selected presets, not from a preset's settings.
APP_MANAGED = ("from", "version", "print_settings_id", "printer_settings_id", "filament_settings_id")
# ... and the two of those a preset file also carries (a filament preset has from /
# version of its own): the new fixture keeps the cube's, as a project the app wrote.
PROJECT_MANAGED = ("from", "version")
# A manifest of differences from the system preset never names these (the cube's does
# not name from / version although they differ; the ids are the slicer's own ignore
# list, PresetBundle.cpp:2493).
MANIFEST_SKIP = frozenset(PRESET_META) | frozenset(APP_MANAGED)
RECORDED = ("layer_height", "line_width", "nozzle_diameter", "travel_speed", "inner_wall_speed",
            "outer_wall_speed", "sparse_infill_speed", "top_surface_speed", "initial_layer_speed",
            "filament_max_volumetric_speed", "wall_loops", "sparse_infill_density", "enable_support",
            "enable_prime_tower")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vector(value):
    return list(value) if isinstance(value, list) else [value]


def brief(value, limit=120):
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= limit else text[:limit] + "..."


# ---- vendor tree ---------------------------------------------------------

def load_preset(path):
    raw = path.read_bytes()
    # Some vendor files start with a UTF-8 BOM (fdm_process_common.json, the
    # 0.20mm Standard process preset): plain utf-8 would leave it inside the first key.
    return json.loads(raw.decode("utf-8-sig"))


def preset_path(root, sub, name):
    for folder in (root / VENDOR / sub, root):   # the sub-directory first, then the parent
        if (folder / (name + ".json")).is_file():
            return folder / (name + ".json")
    raise KeyError("preset_not_in_tree: %s / %s" % (sub, name))


def chain(root, sub, name):
    """[(path, settings)] from the leaf up; `inherits` is followed until a preset has none."""
    links, seen = [], set()
    while name:
        require(name not in seen, "inherits_cycle:" + name)
        seen.add(name)
        path = preset_path(root, sub, name)
        links.append((path, load_preset(path)))
        name = links[-1][1].get("inherits")
    return links


def unescape(text):
    """A preset file keeps a multiline value in C-escaped form ("\\n", "\\\""); the app
    holds it unescaped - with the escapes resolved as the slicer does (Config.cpp:123),
    the vendored presets' start / end / change G-code equal the cube's byte for byte."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            i += 1
            out.append("\r" if text[i] == "r" else "\n" if text[i] == "n" else text[i])
        else:
            out.append(text[i])
        i += 1
    return "".join(out)


def flatten(links, follow=True):
    """The chain's settings, the child over the parent. follow=False reads the leaf alone."""
    values = {}
    for _path, layer in (reversed(links) if follow else links[:1]):
        values.update(layer)
    plain = lambda value: unescape(value) if isinstance(value, str) else (
        [unescape(entry) if isinstance(entry, str) else entry for entry in value] if isinstance(value, list) else value)
    return {key: plain(value) for key, value in values.items() if key not in PRESET_META}


def filament_chain(root, name):
    """(links, fallback name or None) of one filament preset. A name the tree does not
    carry is matched through the presets' renamed_from, then by its family: the one U1
    preset of the same material that has the fixture's nozzle."""
    folder = root / VENDOR / "filament"
    on_disk = sorted(folder.glob("*.json"))
    if (folder / (name + ".json")).is_file():
        return chain(root, "filament", name), None
    renamed = [path for path in on_disk
               if name in str(load_preset(path).get("renamed_from", "")).split(";")]
    family = name.split(" @")[0] + " @"
    kindred = [path for path in on_disk if path.stem.startswith(family) and "U1" in path.stem]
    same_nozzle = [path for path in kindred if name.split(" @")[-1] in path.stem]
    picked = renamed or same_nozzle or kindred
    require(len(picked) == 1, "filament_preset_not_in_tree: %s (candidates %r)" % (name, [p.stem for p in picked]))
    return chain(root, "filament", picked[0].stem), picked[0].stem


def one(value, variants=None, key=None):
    """A vendor filament value is a list (the per-extruder form) whose first entry is the
    value. A longer list is the flow-variant form [standard, high_flow] the 2.4.1 presets
    use in process presets too; its first entry is the standard variant."""
    if isinstance(value, list) and value:
        if len(value) > 1 and variants is not None:
            variants.add(key)
        return value[0]
    return value


def view(machine, process, filaments, variants=None):
    """The project-format config of a preset trio: one value per key, a filament key as
    one entry per extruder (None where that extruder's preset does not define it) - a
    scalar again when every extruder carries the same value."""
    out = dict(machine)
    out.update({COMPATIBLE_ALIAS.get(key, key): value for key, value in process.items()})
    for key in sorted(set().union(*filaments)):
        entries = [one(preset[key], variants, key) if key in preset else None for preset in filaments]
        out[key] = entries[0] if None not in entries and all(entry == entries[0] for entry in entries) else entries
    return out


def describe(root, links):
    return {"name": links[0][1]["name"],
            "chain": [path.relative_to(root).as_posix() for path, _settings in links]}


# ---- comparison ----------------------------------------------------------

def stretch(values, count):
    """`count` entries: a shorter vector repeats its last entry, a longer one is cut."""
    values = values[:count]
    return values + [values[-1]] * (count - len(values))


def disagreements(left, right):
    """Positions where two values of one key both carry a value and the values differ.
    A scalar is a one-entry vector; None (a preset that does not define the key for
    that extruder) says nothing and never counts."""
    count = max(len(vector(left)), len(vector(right)))
    left, right = stretch(vector(left), count), stretch(vector(right), count)
    return [i for i in range(count) if left[i] is not None and right[i] is not None and left[i] != right[i]]


def differs(fixture, have, keys):
    """The keys of `keys` whose fixture value the view defines and does not reproduce."""
    return [key for key in keys if key in have and disagreements(fixture[key], have[key])]


def classify(fixture, have):
    """{equal, differ: [{key, fixture, chain}], fixture_only, chain_only} of a project
    config against one flattened view."""
    return {"equal": sum(1 for key in fixture if key in have and not disagreements(fixture[key], have[key])),
            "differ": [{"key": key, "fixture": brief(fixture[key]), "chain": brief(have[key])}
                       for key in differs(fixture, have, fixture)],
            "fixture_only": sum(1 for key in fixture if key not in have),
            "chain_only": sorted(set(have) - set(fixture))}


# ---- port ----------------------------------------------------------------

def take(before, have):
    """The chain's value in the fixture's shape: a scalar stays a scalar (the chain's
    first entry - the 2.4.1 presets write some speeds as [standard, high_flow]); a
    vector keeps the fixture's length; a position the chain leaves open keeps the
    fixture's entry."""
    have = vector(have)
    if not isinstance(before, list):
        return before if not have or have[0] is None else str(have[0])
    have = stretch(have, len(before))
    return [str(have[i]) if have[i] is not None else before[i] for i in range(len(before))]


def port(fixture, cube, std, filament_keys):
    """(new config, changed keys, overridden customisations, forced notes, keys only
    the 0.4 chain defines)."""
    new = dict(fixture)
    changed, overrode = [], []
    for key, value in fixture.items():
        if key in PROJECT_MANAGED:
            continue          # from / version say who wrote the project, not what it holds
        if key not in cube or key not in std or not disagreements(cube[key], std[key]):
            continue          # undefined on a side, or the chains agree: nothing to port
        ported = take(value, std[key])
        if ported != value:
            changed.append(key)
        if disagreements(value, cube[key]):
            overrode.append({"key": key, "fixture": brief(value), "chain08": brief(cube[key]),
                             "chain04": brief(std[key])})
        new[key] = ported
    # The ids and every key the chosen presets define, customised or not: the new
    # fixture is the plain preset. filament_type is one of those keys.
    targets = {"print_settings_id": STD_PROCESS, "printer_settings_id": STD_PRINTER,
               "filament_settings_id": [STD_F1] + [STD_F2] * (len(fixture["filament_settings_id"]) - 1)}
    for key in sorted(filament_keys):
        if key in fixture and key not in targets and key not in PROJECT_MANAGED:
            targets[key] = take(fixture[key], std[key])
    forced, forced_over = [], []
    overridden = [row["key"] for row in overrode]
    for key, value in targets.items():
        if not isinstance(fixture[key], list):
            require(not isinstance(value, list), "scalar key would become a vector: " + key)
        else:
            require(len(value) == len(fixture[key]), "vector length changed: " + key)
        if value == new[key]:
            continue
        if key not in changed:
            forced.append(key)
        if key not in overridden and disagreements(fixture[key], cube.get(key)):
            forced_over.append({"key": key, "fixture": brief(fixture[key]), "chain08": brief(cube.get(key)),
                                "value04": brief(value)})
        new[key] = value
    # Keys only the 0.4 chain defines: the rule keeps the cube's value, which is then
    # not the preset's. Listed, not changed - the rule is the user's. The manifest
    # (manifest()) names them, so the app keeps them instead of resetting them on load.
    single = [{"key": key, "fixture": brief(fixture[key]), "chain04": brief(std[key])}
              for key in fixture if key in std and key not in cube
              and key not in targets and disagreements(new[key], std[key])]
    return new, changed + forced, overrode, forced_over, single


def differing(new, settings, value_of):
    """The keys a preset defines whose value the config does not carry at `value_of`."""
    return {key for key in settings if key in new and key not in MANIFEST_SKIP
            and take(value_of(key), settings[key]) != value_of(key)}


def at_filament(new, index):
    """The config's entry of a key for filament `index` (0-based)."""
    return lambda key: new[key][index] if isinstance(new[key], list) else new[key]


def manifest(new, process, filaments, machine):
    """different_settings_to_system of `new` against its own presets, the way the app
    writes it (PresetBundle::full_fff_config -> dirty_options_without_option_list,
    Preset.cpp:3182): per preset the keys it defines whose value the config does not
    carry, sorted and ';'-joined - the print, one entry per filament, the printer.
    A value counts as carried when it is the preset's in the config's own shape (a
    flow-variant speed vector is carried by its standard entry)."""
    whole = lambda key: new[key]
    sections = [differing(new, process, whole)]
    sections += [differing(new, preset, at_filament(new, index)) for index, preset in enumerate(filaments)]
    sections.append(differing(new, machine, whole))
    return [";".join(sorted(keys)) for keys in sections]


MANIFEST_SECTIONS = ("print", "filament_1", "filament_2", "filament_3", "filament_4", "filament_5", "printer")

# What the 2.4.0 build writes into different_settings_to_system when a project of
# this shape is loaded and saved untouched (the first save-only controls, 2026-11-24).
APP_MANIFEST = ["mixed_filament_definitions", "", "", "", "", "", ""]


def check_manifest(value, new, process, filaments, machine):
    """Both ways, read back from the serialised strings: every key the manifest names
    differs from the preset, and every differing key is named."""
    presets = [process, *filaments, machine]
    require(len(value) == len(presets) == len(MANIFEST_SECTIONS), "manifest has an entry per preset")
    for index, (text, settings) in enumerate(zip(value, presets)):
        value_of = at_filament(new, index - 1) if 1 <= index <= len(filaments) else (lambda key: new[key])
        named = {key for key in text.split(";") if key}
        expected = differing(new, settings, value_of)
        require(named == expected, "manifest %s names %r, the config differs in %r"
                % (MANIFEST_SECTIONS[index], sorted(named), sorted(expected)))
    return {name: [key for key in text.split(";") if key]
            for name, text in zip(MANIFEST_SECTIONS, value)}


# ---- serialisation and archive ------------------------------------------

def dump(config):
    """The app's project form: indent 4, CRLF line ends, a CRLF after the closing brace
    (the app writes the member in text mode). Checked against the cube's own bytes
    before it is used."""
    return (json.dumps(config, indent=4, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode("utf-8")


def build_archive(source, config):
    """The source archive with `config` in place of its project settings: same members,
    same order, compression, attributes and timestamps; every other member is the
    source's bytes."""
    original = zipfile.ZipFile(io.BytesIO(source))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compresslevel=9) as out:
        for info in original.infolist():
            clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.create_system = info.create_system        # ZipInfo would pick the host's
            out.writestr(clone, config if info.filename == CONFIG else original.read(info.filename))
    return buffer.getvalue()


def check_archive(source, built, config):
    before, after = zipfile.ZipFile(io.BytesIO(source)), zipfile.ZipFile(io.BytesIO(built))
    require(after.namelist() == MEMBERS, "member list or order changed")
    require(after.testzip() is None, "archive is corrupt")
    for name in MEMBERS:
        if name != CONFIG:
            require(after.read(name) == before.read(name), "member bytes changed: " + name)
    require(len({info.date_time for info in before.infolist()}) == 1, "source members do not share one timestamp")
    require(len({info.date_time for info in after.infolist()}) == 1, "output timestamps are not fixed")
    return len(after.read(CONFIG))


# ---- sanity assertions ---------------------------------------------------

def value_kind(entry):
    """'number' | 'percent' | 'nil' | None. Speeds and accelerations are mm/s, a
    percentage of another value, or `nil` (the U1 toolchanger retracts nothing:
    filament_retraction_speed is 'nil' in the cube)."""
    if entry == "nil":
        return "nil"
    try:
        Decimal(entry[:-1] if entry.endswith("%") else entry)
    except InvalidOperation:
        return None
    return "percent" if entry.endswith("%") else "number"


def assert_sane(new, fixture):
    require(list(new) == list(fixture), "keys were added, removed or reordered")
    for key, before in fixture.items():
        after = new[key]
        require(type(after) is type(before), "value type changed: " + key)
        require(all(type(entry) is str for entry in vector(after)), "value is not a string: " + key)
        require(not isinstance(before, list) or len(after) == len(before), "vector length changed: " + key)
    require(len(new) == 578, "key count is not 578")
    require(new["nozzle_diameter"] == ["0.4"] * len(new["nozzle_diameter"]), "nozzle_diameter is not all 0.4")
    require(new["layer_height"] == "0.2", "layer_height is not 0.2")
    # The preset's own value: 0.20mm Standard @Snapmaker U1 (0.4 nozzle) sets the first
    # layer to 0.25 in the 2.4.1 tree and in the repo's vendored copy alike.
    require(new["initial_layer_print_height"] == "0.25", "initial_layer_print_height is not the preset's 0.25")
    require(Decimal("0.2") < Decimal(new["line_width"]) <= Decimal("0.45"), "line_width is not in (0.2, 0.45]")
    units = {}
    for key, value in new.items():
        if "speed" not in key and "accel" not in key:
            continue
        for entry in vector(value):
            kind = value_kind(entry)
            require(kind is not None, "speed / acceleration value is not a number: %s=%r" % (key, entry))
            if kind != "number":
                units.setdefault(key, []).append(entry)
    require(json.loads(dump(new).decode("utf-8")) == new, "config does not round-trip")
    require(new["print_settings_id"] == STD_PROCESS and new["printer_settings_id"] == STD_PRINTER,
            "preset ids were not set")
    require(new["filament_settings_id"] == [STD_F1] + [STD_F2] * 4, "filament ids were not set")
    require(new["filament_type"] == ["PLA"] * 5, "filament_type is not all PLA")
    require(all(new[key] == fixture[key] for key in PROJECT_MANAGED), "from / version were changed")
    return units


# ---- main ----------------------------------------------------------------

def trio(root, printer, process, filament_links):
    return {"printer": chain(root, "machine", printer), "process": chain(root, "process", process),
            "filaments": filament_links}


def project_view(links, order, follow=True, variants=None):
    """The flattened view of a trio; `order` names one filament preset per extruder."""
    flat = lambda item: flatten(item, follow)
    return view(flat(links["printer"]), flat(links["process"]),
                [flat(links["filaments"][name]) for name in order], variants)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-sha256", action="store_true", help="print the output's sha256, write nothing")
    args = parser.parse_args()
    source = (REPO / LAYER_FIXTURE).read_bytes()
    require(hashlib.sha256(source).hexdigest() == LAYER_FIXTURE_SHA256, "cube fixture is not the pinned one")
    original = zipfile.ZipFile(io.BytesIO(source))
    require(original.namelist() == MEMBERS, "cube fixture member list changed")
    raw = original.read(CONFIG)
    fixture = json.loads(raw.decode("utf-8"))
    require(dump(fixture) == raw, "the serialiser does not reproduce the cube's config bytes")
    require(all(type(value) in (str, list) for value in fixture.values()), "config value is not a string or a list")
    slots = fixture["filament_settings_id"]
    cube_names = list(dict.fromkeys(slots))

    # The two chains. The cube's filament presets are the names its config carries.
    cube_links, fallback = trio(PROFILES, CUBE_PRINTER, CUBE_PROCESS, {}), {}
    for name in cube_names:
        cube_links["filaments"][name], fallback[name] = filament_chain(PROFILES, name)
    cube = project_view(cube_links, slots)
    std_links = trio(PROFILES, STD_PRINTER, STD_PROCESS, {})
    for name in (STD_F1, STD_F2):
        std_links["filaments"][name], _ = filament_chain(PROFILES, name)
    std_order = [STD_F1] + [STD_F2] * (len(slots) - 1)
    flow_variants = set()
    std = project_view(std_links, std_order, variants=flow_variants)
    filament_keys = set().union(*(flatten(links) for links in std_links["filaments"].values()))

    # 1. Validation of the flattener on the cube, and its red proof: the same keys read
    #    from the leaf presets alone.
    validation = classify(fixture, cube)
    keys = sorted(set(cube) & set(fixture))
    leaf = project_view(cube_links, slots, follow=False)
    red = {"keys": len(keys), "flattened_not_reproduced": len(validation["differ"]),
           "leaf_only_equal": sum(1 for key in keys if key in leaf and not disagreements(fixture[key], leaf[key])),
           "leaf_only_undefined": sum(1 for key in keys if key not in leaf)}
    red["leaf_only_differ"] = len(keys) - red["leaf_only_equal"] - red["leaf_only_undefined"]
    red["leaf_only_not_reproduced"] = red["leaf_only_differ"] + red["leaf_only_undefined"]
    # Where the remaining differences come from. The repo's vendored tree is the preset
    # set the datadir seed carries: a key it reproduces is a preset that changed between
    # the slicer versions, not a customisation of the cube.
    reproduced = None
    vendored = REPO / "resources"
    if (vendored / VENDOR).is_dir():
        try:
            old_links = trio(vendored, CUBE_PRINTER, fixture["print_settings_id"], {})
            for name in cube_names:
                old_links["filaments"][name], _ = filament_chain(vendored, name)
            old = project_view(old_links, slots)
            reproduced = [row["key"] for row in validation["differ"]
                          if row["key"] in old and not disagreements(fixture[row["key"]], old[row["key"]])]
        except KeyError:
            reproduced = None       # the vendored tree cannot resolve the cube's presets
    names = [row["key"] for row in validation["differ"]]
    validation.update(
        compared=len(keys),
        differ_kinds={key: ("app_managed" if key in APP_MANAGED else
                            "preset_changed_between_trees" if reproduced and key in reproduced else
                            "value_of_the_saving_slicer") for key in names})

    # 2. Port, force, manifest, assert, build.
    new, changed, overrode, forced_over, single = port(fixture, cube, std, filament_keys)
    # different_settings_to_system: the app writes this manifest at save, from the
    # project as it loaded it, against the presets it resolved for it. Measured on
    # the 2.4.0 build with both fixtures loaded and saved untouched (VM c88272e,
    # fa706g3 7c067c0, the first save-only controls): ['mixed_filament_definitions',
    # '', '', '', '', '', ''] for the cube AND for the first build of this fixture,
    # whose own manifest named 6 print and 3 printer keys. The presets load as the
    # project's own (their names get "(fixture.3mf)"), every project value is kept,
    # and the manifest names only the app-managed key. Carrying the computed list
    # made the preserved-settings rule refuse the plain save (the app's list is not
    # a superset of it: pilot_dirty_manifest_out_of_scope). So the fixture carries
    # what the app will write; where this config differs from the 0.4 presets of
    # the host's 2.4.1 tree is kept for the report.
    process04, machine04 = flatten(std_links["process"]), flatten(std_links["printer"])
    filaments04 = [flatten(std_links["filaments"][name]) for name in std_order]
    differs_from_chain = manifest(new, process04, filaments04, machine04)
    check_manifest(differs_from_chain, new, process04, filaments04, machine04)
    new["different_settings_to_system"] = list(fixture["different_settings_to_system"])
    require(new["different_settings_to_system"] == APP_MANIFEST,
            "the cube's manifest is not the measured one: %r" % (fixture["different_settings_to_system"],))
    if "different_settings_to_system" not in changed:
        changed.append("different_settings_to_system")
    manifest_names = {name: [key for key in text.split(";") if key]
                      for name, text in zip(MANIFEST_SECTIONS, differs_from_chain)}
    units = assert_sane(new, fixture)
    built = build_archive(source, dump(new))
    config_size = check_archive(source, built, new)
    sha = hashlib.sha256(built).hexdigest()
    if args.print_sha256:
        print(sha)
        return 0
    pinned = getattr(agent_protocol, "STD_FIXTURE_SHA256", None)
    require(pinned is not None, "pin_missing: add STD_FIXTURE_SHA256 to harness/agent_protocol.py "
                                 "(sha256 " + sha + ")")
    require(sha == pinned, "pin_mismatch: built %s, pinned %s" % (sha, pinned))
    target = REPO / OUTPUT
    rewritten = not target.is_file() or target.read_bytes() != built
    if rewritten:
        target.write_bytes(built)
    report = {
        "source": {"path": LAYER_FIXTURE, "sha256": LAYER_FIXTURE_SHA256, "size": len(source)},
        "output": {"path": OUTPUT, "sha256": sha, "size": len(built), "members": len(MEMBERS),
                   "config_size": config_size, "rewritten": rewritten},
        "presets": {
            "tree": str(PROFILES), "vendor": VENDOR,
            "cube": {"printer": describe(PROFILES, cube_links["printer"]),
                     "process": describe(PROFILES, cube_links["process"]),
                     "filaments": [dict(describe(PROFILES, cube_links["filaments"][name]), fallback=fallback[name])
                                   for name in cube_names]},
            "std": {"printer": describe(PROFILES, std_links["printer"]),
                    "process": describe(PROFILES, std_links["process"]),
                    "filaments": [{"extruders": [1], "why": WHY_F1, **describe(PROFILES, std_links["filaments"][STD_F1])},
                                  {"extruders": [2, 3, 4, 5], "why": WHY_F2,
                                   **describe(PROFILES, std_links["filaments"][STD_F2])}]}},
        "flattener_validation": dict(validation, red_proof=red, vendored_tree_reproduces=reproduced),
        "port": {"changed_count": len(changed), "changed": changed, "overrode_customised": overrode,
                 "forced_over_customised": forced_over, "kept_where_only_chain04_defines": single,
                 "cut_to_scalar": sorted(key for key in changed if not isinstance(fixture[key], list)
                                         and isinstance(std[key], list) and len(std[key]) > 1)
                                         + sorted(flow_variants),
                 "kept_from_cube": {key: brief(fixture[key]) for key in
                                    ("filament_ids", "from", "version") if fixture[key] == new[key]}},
        "different_settings_to_system": {"value": new["different_settings_to_system"],
                                         "measured_on": "VM c88272e, fa706g3 7c067c0",
                                         "count": sum(len(keys) for keys in manifest_names.values()),
                                         "differs_from_0.4_chain": manifest_names,
                                         "cube": fixture["different_settings_to_system"]},
        "settings": {key: new[key] for key in RECORDED},
        "initial_layer_print_height": new["initial_layer_print_height"],
        "speed_values_not_mm_s": units,
        "assertions": "ok",
    }
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
