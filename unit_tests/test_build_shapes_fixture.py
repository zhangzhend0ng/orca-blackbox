"""The Feishu shapes plate: the committed fixture is what the tool builds from the cube
template, the ids follow whatever the template holds, and every required check
goes red on a deliberately broken variant - a green run of the tool then means
something. Generated projects only; no application, no GUI."""
import re
import subprocess
import sys
import urllib.parse

import pytest

from collections.abc import Callable

from tools import build_shapes_fixture as bf

TEMPLATE_PATH = bf.ROOT / bf.DEFAULT_TEMPLATE
FIXTURE_PATH = bf.ROOT / bf.DEFAULT_OUT
TEMPLATE = TEMPLATE_PATH.read_bytes()

MODEL = bf.MODEL_MEMBER
RELS = bf.MODEL_RELS_MEMBER
SETTINGS = bf.SETTINGS_MEMBER
CUBE = "3D/Objects/立方体_1.model"
TRIANGLE = re.compile(r'(?m)^ *<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"/>\n')
VERTEX = re.compile(r'(?m)^ *<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>\n')


def build(raw: bytes = TEMPLATE) -> bytes:
    return bf.build(bf.read_template(raw))


def quiet(_line: str) -> None:
    pass


def replace_once(text: str, old: str, new: str) -> str:
    """A text with `old` replaced once; the test fails if `old` is not there (no silent no-op mutation)."""
    assert old in text, f"{old!r} is not in the text, the mutation would change nothing"
    return text.replace(old, new, 1)


def entries_of(raw: bytes) -> list[bf.Entry]:
    return bf.read_archive(raw, bf.ValidationError)[0]


def read_member(raw: bytes, member: str) -> bytes:
    return next(entry for entry in entries_of(raw) if entry.name == member).content(bf.ValidationError)


def with_member(raw: bytes, member: str, content: bytes) -> bytes:
    """The same archive with one member's content replaced; every other record stays as it is."""
    return bf.write_archive([
        entry.clone(entry.name, content, entry.deflate_level()) if entry.name == member else entry
        for entry in entries_of(raw)])


def with_renamed_member(raw: bytes, old: str, new: str) -> bytes:
    return bf.write_archive([
        entry.clone(new, entry.content(bf.ValidationError), entry.deflate_level()) if entry.name == old else entry
        for entry in entries_of(raw)])


def edit_member(raw: bytes, member: str, edit: Callable[[str], str]) -> bytes:
    return with_member(raw, member, edit(read_member(raw, member).decode("utf-8")).encode("utf-8"))


def edit_text(raw: bytes, member: str, edit: Callable[[bytes], bytes]) -> bytes:
    """The same archive with one member's bytes replaced by what `edit` returns."""
    return with_member(raw, member, edit(read_member(raw, member)))


def triangle_line(v1: str, v2: str, v3: str) -> str:
    return f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>\n'


def first_triangle(text: str, replacement: Callable[..., str]) -> str:
    return TRIANGLE.sub(lambda found: replacement(*found.groups()), text, count=1)


def first_vertex(text: str, replacement: Callable[..., str]) -> str:
    return VERTEX.sub(lambda found: replacement(*found.groups()), text, count=1)


def flipped_byte(data: bytes, position: int) -> bytes:
    return data[:position] + bytes([data[position] ^ 1]) + data[position + 1:]


def facts(raw: bytes) -> dict[str, list[str | None]]:
    """Ids, names and paths of a project, read from its members."""
    roots = {entry.name: bf.xml_root(entry.content(bf.ValidationError), entry.name, bf.ValidationError)
             for entry in entries_of(raw) if entry.content(bf.ValidationError).lstrip()[:1] == b"<"}
    objects = bf.find_all(roots[MODEL], "resources", "object")
    components = [bf.find_all(obj, "components", "component")[0] for obj in objects]
    relations = [rel for rel in roots[RELS] if bf.short_name(rel.tag) == "Relationship"]
    settings = roots[SETTINGS]
    setting_objects = bf.find_all(settings, "object")
    return {
        "object_ids": [bf.attributes(obj).get("id") for obj in objects],
        "object_uuids": [bf.attributes(obj).get("UUID") for obj in objects],
        "volume_ids": [bf.attributes(component).get("objectid") for component in components],
        "paths": [bf.attributes(component).get("path") for component in components],
        "component_uuids": [bf.attributes(component).get("UUID") for component in components],
        "item_uuids": [bf.attributes(item).get("UUID") for item in bf.find_all(roots[MODEL], "build", "item")],
        "rel_ids": [bf.attributes(rel).get("Id") for rel in relations],
        "targets": [bf.attributes(rel).get("Target") for rel in relations],
        "names": [bf.metadata_of(obj).get("name") for obj in setting_objects],
        "extruders": [bf.metadata_of(obj).get("extruder") for obj in setting_objects],
        "identities": [bf.metadata_of(inst).get("identify_id")
                       for inst in bf.find_all(settings, "plate", "model_instance")],
        "part_ids": [bf.attributes(bf.find_all(obj, "part")[0]).get("id") for obj in setting_objects],
    }


def variant_template(percent_escaped: bool) -> bytes:
    """The cube template with other ids: object 7, volume 6, backup id 10, file index 10, rel-4, identify 7, extruder 2."""
    template = bf.read_template(TEMPLATE)
    path = "/3D/Objects/立方体_10.model"
    if percent_escaped:
        path = urllib.parse.quote(path)
    model = replace_once(template.contents[MODEL].decode("utf-8"), '<object id="2" p:UUID="00000001-',
                         '<object id="7" p:UUID="0000000a-')
    model = replace_once(model, 'p:path="/3D/Objects/立方体_1.model" objectid="1" p:UUID="00010000-',
                         f'p:path="{path}" objectid="6" p:UUID="000a0000-')
    model = replace_once(model, '<item objectid="2" p:UUID="00000002-', '<item objectid="7" p:UUID="00000007-')
    rels = replace_once(template.contents[RELS].decode("utf-8"), 'Target="/3D/Objects/立方体_1.model" Id="rel-1"',
                        f'Target="{path}" Id="rel-4"')
    mesh = replace_once(template.contents[CUBE].decode("utf-8"), '<object id="1" p:UUID="00010000-',
                        '<object id="6" p:UUID="000a0000-')
    settings = replace_once(template.contents[SETTINGS].decode("utf-8"), '<object id="2">', '<object id="7">')
    settings = replace_once(settings, '<metadata key="extruder" value="1"/>', '<metadata key="extruder" value="2"/>')
    settings = replace_once(settings, '<part id="1"', '<part id="6"')
    settings = replace_once(settings, 'key="object_id" value="2"', 'key="object_id" value="7"')
    settings = replace_once(settings, 'key="identify_id" value="90"', 'key="identify_id" value="7"')
    settings = replace_once(settings, '<assemble_item object_id="2"', '<assemble_item object_id="7"')
    changed = {CUBE: ("3D/Objects/立方体_10.model", mesh), MODEL: (MODEL, model),
               RELS: (RELS, rels), SETTINGS: (SETTINGS, settings)}
    return bf.write_archive([
        entry.clone(changed[entry.name][0], changed[entry.name][1].encode("utf-8"), entry.deflate_level())
        if entry.name in changed else entry
        for entry in template.entries])


def test_committed_fixture_is_what_the_tool_builds() -> None:
    assert FIXTURE_PATH.read_bytes() == build()


def test_valid_project_passes_every_check() -> None:
    lines: list[str] = []
    objects = bf.validate(build(), bf.read_template(TEMPLATE), lines.append)
    assert [placed.shape.name for placed in objects] == ["立方体", "圆柱体", "搭桥", "悬垂台阶", "立方体2"]
    assert any("9 of 9" in line for line in lines) and any("smallest 14 mm" in line for line in lines)


@pytest.mark.parametrize("edit,message", [
    pytest.param(lambda text: first_triangle(text, lambda a, b, c: triangle_line(a, c, b)),
                 "directed edges occur twice", id="one-triangle-wound-backwards"),
    pytest.param(lambda text: first_triangle(text, lambda a, b, c: ""),
                 "do not join exactly two triangles", id="one-triangle-missing"),
    pytest.param(lambda text: first_triangle(text, lambda a, b, c: triangle_line(a, a, c)),
                 "repeats a vertex", id="triangle-repeats-a-vertex"),
    pytest.param(lambda text: first_triangle(text, lambda a, b, c: triangle_line(a, b, c) * 2),
                 "is a duplicate", id="triangle-entered-twice"),
    pytest.param(lambda text: TRIANGLE.sub(lambda found: triangle_line(found[1], found[3], found[2]), text),
                 "is not positive", id="whole-shell-wound-inside-out"),
    pytest.param(lambda text: first_vertex(text, lambda x, y, z: f'     <vertex x="11" y="{y}" z="{z}"/>\n'),
                 "against design", id="one-vertex-moved"),
    pytest.param(lambda text: first_vertex(text, lambda x, y, z: f'     <vertex x="{x}.0000001" y="{y}" z="{z}"/>\n'),
                 "at most 6 decimals", id="coordinate-with-a-seventh-decimal"),
    pytest.param(lambda text: first_vertex(text, lambda x, y, z: f'     <vertex x="{x}" y="{y}" z="{z}"/>\n'
                                                              + '     <vertex x="0" y="0" z="5"/>\n'),
                 "vertices no triangle uses", id="vertex-no-triangle-uses"),
])
def test_broken_mesh_is_rejected(edit: Callable[[str], str], message: str) -> None:
    with pytest.raises(bf.ValidationError, match=message):
        bf.validate(edit_member(build(), CUBE, edit), bf.read_template(TEMPLATE), quiet)


@pytest.mark.parametrize("member,change,message", [
    pytest.param("Metadata/project_settings.config", lambda data: flipped_byte(data, 200),
                 "content differs from the template", id="project-settings-changed"),
    pytest.param("Metadata/plate_1.png", lambda data: flipped_byte(data, 40),
                 "content differs from the template", id="thumbnail-changed"),
    pytest.param(MODEL, lambda data: replace_once(data.decode("utf-8"), 'p:path="/3D/Objects/搭桥_3.model"',
                                                  'p:path="/3D/Objects/搭桥_3x.model"').encode("utf-8"),
                 "disagree", id="component-path-disagrees-with-the-relationship"),
    pytest.param(MODEL, lambda data: replace_once(data.decode("utf-8"), "1 0 0 0 1 0 0 0 1 125 135 0",
                                                  "1 0 0 0 1 0 0 0 1 125 136 0").encode("utf-8"),
                 "build item 2 has transform", id="build-item-moved"),
    pytest.param(SETTINGS, lambda data: replace_once(data.decode("utf-8"), '<metadata key="extruder" value="3"/>',
                                                     '<metadata key="extruder" value="1"/>').encode("utf-8"),
                 "has extruder", id="extruder-not-applied"),
    pytest.param(SETTINGS, lambda data: replace_once(data.decode("utf-8"), '<metadata key="name" value="搭桥"/>',
                                                     '<metadata key="name" value="桥"/>').encode("utf-8"),
                 "is named", id="object-renamed"),
    pytest.param(SETTINGS, lambda data: re.sub(r'(?s)  <object id="6">.*?  </object>\n', "",
                                               data.decode("utf-8")).encode("utf-8"),
                 "not 5 objects", id="one-object-missing"),
    pytest.param(SETTINGS, lambda data: replace_once(data.decode("utf-8"), '1 0 0 0 1 0 0 0 1 165 135 0" offset',
                                                     '1 0 0 0 1 0 0 0 1 165 134 0" offset').encode("utf-8"),
                 "assemble_item 3 is not the template's", id="assemble-transform-differs-from-the-build-item"),
    pytest.param(SETTINGS, lambda data: replace_once(data.decode("utf-8"), 'key="identify_id" value="94"',
                                                     'key="identify_id" value="93"').encode("utf-8"),
                 "model_instance 4 is not the template's", id="identify-id-collides-with-another-object"),
    pytest.param(SETTINGS, lambda data: replace_once(data.decode("utf-8"),
                                                     '    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n',
                                                     "").encode("utf-8"),
                 "template line", id="a-template-line-of-the-plate-dropped"),
])
def test_broken_project_is_rejected(member: str, change: Callable[[bytes], bytes], message: str) -> None:
    with pytest.raises(bf.ValidationError, match=message):
        bf.validate(edit_text(build(), member, change), bf.read_template(TEMPLATE), quiet)


@pytest.mark.parametrize("make,message", [
    pytest.param(lambda: b"not a zip at all", "zip:", id="not-a-zip"),
    pytest.param(lambda: TEMPLATE[:-10], "zip:", id="a-zip-cut-short"),
    pytest.param(build, "exactly one top-level object", id="a-project-that-already-has-five-objects"),
    pytest.param(lambda: with_member(TEMPLATE, MODEL, b"<!DOCTYPE x [\n" + read_member(TEMPLATE, MODEL)),
                 "DTD or entity", id="a-member-with-a-DTD"),
    pytest.param(lambda: with_renamed_member(TEMPLATE, CUBE, "../立方体_1.model"),
                 "not a plain package path", id="a-member-name-that-leaves-the-package"),
    pytest.param(lambda: bf.write_archive([entry for entry in entries_of(TEMPLATE) if entry.name != CUBE]),
                 "not a member of the zip", id="the-components-document-missing-from-the-zip"),
])
def test_template_the_tool_refuses(make: Callable[[], bytes], message: str) -> None:
    with pytest.raises(bf.TemplateError, match=message):
        bf.read_template(make())


def test_ids_follow_the_template_not_a_constant() -> None:
    template = variant_template(percent_escaped=False)
    output = build(template)
    bf.validate(output, bf.read_template(template), quiet)
    found = facts(output)
    assert found["object_ids"] == ["7", "8", "9", "10", "11"]
    assert found["volume_ids"] == found["part_ids"] == ["6", "7", "8", "9", "10"]
    assert found["object_uuids"][0] == "0000000a-61cb-4c03-9d28-80fed5dfa1dc"
    assert found["object_uuids"][4] == "0000000e-61cb-4c03-9d28-80fed5dfa1dc"
    assert found["component_uuids"][4] == "000e0000-b206-40ff-9872-83e8017abed1"
    assert found["item_uuids"] == [f"0000000{digit}-b1ec-4553-aec9-835e5b724bb4" for digit in "789ab"]
    assert found["paths"] == found["targets"] == [
        "/3D/Objects/立方体_10.model", "/3D/Objects/圆柱体_11.model", "/3D/Objects/搭桥_12.model",
        "/3D/Objects/悬垂台阶_13.model", "/3D/Objects/立方体2_14.model"]
    assert found["rel_ids"] == ["rel-4", "rel-5", "rel-6", "rel-7", "rel-8"]
    assert found["identities"] == ["7", "8", "9", "10", "11"]
    assert found["extruders"] == ["2", "2", "2", "2", "3"]


def test_percent_escaped_template_keeps_that_style() -> None:
    template = variant_template(percent_escaped=True)
    output = build(template)
    bf.validate(output, bf.read_template(template), quiet)
    found = facts(output)
    assert found["paths"] == found["targets"]
    assert found["paths"][0] == urllib.parse.quote("/3D/Objects/立方体_10.model")
    assert all(path is not None and "%" in path for path in found["paths"])


def test_default_template_writes_paths_unescaped() -> None:
    found = facts(build())
    assert found["paths"][2] == "/3D/Objects/搭桥_3.model"
    assert not any(path is not None and "%" in path for path in found["paths"])


def test_run_twice_writes_the_same_bytes(tmp_path, capsys) -> None:
    out = tmp_path / "plate.3mf"
    assert bf.main(["--template", str(TEMPLATE_PATH), "--out", str(out)]) == 0
    first = out.read_bytes()
    assert bf.main(["--template", str(TEMPLATE_PATH), "--out", str(out)]) == 0
    assert out.read_bytes() == first == FIXTURE_PATH.read_bytes()
    assert "existing plate.3mf: byte-identical to this build" in capsys.readouterr().out
    assert [path.name for path in tmp_path.iterdir()] == ["plate.3mf"]   # no temporary file left


def test_out_equal_to_the_template_is_refused_before_any_write(tmp_path, capsys) -> None:
    copy = tmp_path / "cube.3mf"
    copy.write_bytes(TEMPLATE)
    assert bf.main(["--template", str(copy), "--out", str(copy)]) == 1
    assert copy.read_bytes() == TEMPLATE
    assert "must not be the template" in capsys.readouterr().err
    assert TEMPLATE_PATH.read_bytes() == TEMPLATE


def test_missing_template_ends_with_an_error(tmp_path, capsys) -> None:
    assert bf.main(["--template", str(tmp_path / "absent.3mf"), "--out", str(tmp_path / "out.3mf")]) == 1
    assert "cannot read the template" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_checks_survive_python_optimized_mode(tmp_path) -> None:
    """The required checks are calls, not `assert` statements: `python -O` cannot remove them."""
    broken = tmp_path / "broken.3mf"
    broken.write_bytes(edit_member(build(), CUBE, lambda text: first_triangle(text, lambda a, b, c: "")))
    code = ("import sys; from tools import build_shapes_fixture as bf; "
            "bf.validate(open(sys.argv[1], 'rb').read(), "
            "bf.read_template(open(sys.argv[2], 'rb').read()), lambda line: None)")
    done = subprocess.run([sys.executable, "-O", "-B", "-c", code, str(broken), str(TEMPLATE_PATH)],
                          cwd=str(bf.ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 1
    assert "ValidationError" in done.stderr and "do not join exactly two triangles" in done.stderr
