"""Controls for tools/make_assembly_step.py (Feishu #229).

The positive control is the file the tool writes. Every negative control is
that text with one thing changed, or the tool asked for something it must
refuse, and the check has to go red for each.
"""
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tools.make_assembly_step as step  # noqa: E402

# The calibration model of the application: a real AP214 export with comments, entities that
# span lines and B-spline edges. Read where it is; skipped where it is not.
CALIBRATION = Path('C:/coil/Projects/SnapmakerOrca/resources/calib/volumetric_speed/SpeedTestStructure.step')
FIXTURE = ROOT / 'fixtures/assembly.step'


def _write(tmp_path, text, name='broken.step'):
    path = tmp_path / name
    path.write_bytes(text.encode('ascii'))
    return path


def test_the_written_file_passes_its_check(tmp_path):
    first = write = step.write_assembly(tmp_path / 'assembly.step')
    assert step.write_assembly(tmp_path / 'again.step') == dict(write, name='again.step'), 'the bytes change between runs'
    raw = (tmp_path / 'assembly.step').read_bytes()
    assert first['bytes'] == len(raw) == 13829 and raw.decode('ascii') and b'\r' not in raw
    assert raw.startswith(b'ISO-10303-21;\n') and raw.endswith(b'END-ISO-10303-21;\n')
    readings = step.verify_step(tmp_path / 'assembly.step')
    assert readings['failures'] == [] and readings['schema'] == step.SCHEMA and readings['length_unit_mm']
    assert (readings['entities'], readings['references']) == (377, 591)
    assert len(readings['solids']) == 3 and len(readings['colours']) == 3 and readings['geometry_checked']
    assert sorted(readings['colours']) == [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]
    assert [colour for _kind, _target, colour in readings['styled']] == [
        ('Red', (1.0, 0.0, 0.0)), ('Green', (0.0, 1.0, 0.0)), ('Blue', (0.0, 0.0, 1.0))]
    assert [target for _kind, target, _colour in readings['styled']] == readings['solids']
    for name, low in zip(step.SOLIDS, (0.0, 20.0, 40.0)):
        assert (f"{name}: 6 faces, volume 1000 mm3, box [[{low:.1f}, {low + 10:.1f}], [0.0, 10.0], [0.0, 10.0]]"
                in readings['geometry'])


def test_the_fixture_is_what_the_tool_writes():
    if not FIXTURE.is_file():
        pytest.skip('fixtures/assembly.step is not in this checkout')
    assert FIXTURE.read_bytes() == step.assembly_text().encode('ascii')
    assert step.verify_step(FIXTURE)['failures'] == []


def test_cube_edges_and_loops_are_consistent_by_construction():
    """Each of the twelve edges is used forwards once and backwards once, and every face's loop
    turns the way its outward normal says: read back from the text, not from the writer's tables."""
    text = step.assembly_text()
    _header, entities = step.read_step(text)
    flags, volumes = {}, []
    for id_, (name, arguments, _used) in entities.items():
        if name == 'ORIENTED_EDGE':
            edge, flag = step._split(arguments, ',')[3:]
            flags.setdefault(edge, []).append(flag)
    assert len(flags) == 36 and all(sorted(values) == ['.F.', '.T.'] for values in flags.values())
    solids = [f'#{id_}' for id_, (name, _arguments, _used) in entities.items() if name == 'MANIFOLD_SOLID_BREP']
    for solid in solids:
        read = step._solid_geometry(entities, solid)
        assert read['closed'] and read['loops_follow_normals'] and read['lines_follow_edges']
        volumes.append(read['volume_mm3'])
    assert volumes == pytest.approx([1000.0, 1000.0, 1000.0], rel=1e-9)


DANGLING = ("VERTEX_POINT('',#", "VERTEX_POINT('',#999999", 'references that are not defined')
TWICE = ("#2=APPLICATION_PROTOCOL_DEFINITION", "#1=APPLICATION_PROTOCOL_DEFINITION", 'ids defined more than once')
SAME_COLOUR = ("COLOUR_RGB('Green',0,1,0)", "COLOUR_RGB('Green',1,0,0)", 'COLOUR_RGB: 2 different')
UNPAINTED = ("STYLED_ITEM('',(#369),#346)", "STYLED_ITEM('',(#369),#130)", 'do not each carry one STYLED_ITEM')
TURNED_LOOP = ("FACE_OUTER_BOUND('',#81,.T.)", "FACE_OUTER_BOUND('',#81,.F.)", 'not a closed, outward-facing shell')
BACKWARDS_LINE = ("EDGE_CURVE('',#31,#32,#40,.T.)", "EDGE_CURVE('',#31,#32,#40,.F.)", 'not a closed, outward-facing shell')


@pytest.mark.parametrize('old, new, failure', [DANGLING, TWICE, SAME_COLOUR, UNPAINTED, TURNED_LOOP, BACKWARDS_LINE])
def test_the_check_goes_red(tmp_path, old, new, failure):
    text = step.assembly_text()
    assert old in text, 'the control no longer names a record of the file'
    path = _write(tmp_path, text.replace(old, new, 1))
    readings = step.check_step(path)
    assert any(failure in line for line in readings['failures']), readings['failures']
    with pytest.raises(ValueError, match=failure):
        step.verify_step(path)


def test_two_cubes_in_one_place_are_refused(tmp_path, monkeypatch):
    """The cubes' boxes may not overlap: here every cube is written at the first one's place."""
    original = step._cube
    monkeypatch.setattr(step, '_cube', lambda writer, name, _origin, side, directions: original(
        writer, name, (0.0, 0.0, 0.0), side, directions))
    path = _write(tmp_path, step.assembly_text(), 'stacked.step')
    assert any('overlap' in line for line in step.check_step(path)['failures'])


@pytest.mark.parametrize('options', [{'side': 0}, {'gap': 0}, {'gap': -5}, {'side': -1}])
def test_the_writer_refuses_what_cannot_stand_apart(options):
    with pytest.raises(ValueError):
        step.assembly_text(**options)


def test_the_command_line_writes_and_checks(tmp_path):
    path = tmp_path / 'assembly.step'
    assert step.main([str(path)]) == 0 and path.is_file()
    assert step.main(['--check', str(path)]) == 0
    broken = _write(tmp_path, step.assembly_text().replace(*DANGLING[:2], 1))
    assert step.main(['--check', str(broken)]) == 1
    run = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/make_assembly_step.py'), '--check', str(path)],
                         capture_output=True, text=True)
    assert run.returncode == 0 and 'MANIFOLD_SOLID_BREP: 3' in run.stdout and 'COLOUR_RGB: 3 different' in run.stdout


def test_a_real_export_of_the_application_is_read():
    """The calibration model: one white solid written by another tool. Its records are parsed,
    its references all resolve, and the check says what it lacks for this row."""
    if not CALIBRATION.is_file():
        pytest.skip('the calibration model is not on this machine')
    readings = step.check_step(CALIBRATION)
    assert (readings['entities'], readings['references']) == (31430, 35466)
    assert readings['duplicates'] == [] and readings['missing'] == []
    assert readings['solids'] == ['#14'] and readings['colours'] == [(0.964705882352941, 0.964705882352941, 0.952941176470588)]
    assert readings['styled'] == [('MANIFOLD_SOLID_BREP', '#14', ('ABS (White)', (0.964705882352941, 0.964705882352941,
                                                                                0.952941176470588)))]
    assert not readings['geometry_checked'] and 'B_SPLINE_CURVE_WITH_KNOTS' in readings['geometry'][0]
    assert any('MANIFOLD_SOLID_BREP: 1, expected 3' in line for line in readings['failures'])
    assert re.search(r"SHAPE_REPRESENTATION_RELATIONSHIP\('SRR','None',", CALIBRATION.read_text(encoding='ascii'))
