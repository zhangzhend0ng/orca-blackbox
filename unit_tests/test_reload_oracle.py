"""Controls for tests/reload_oracle.py (Feishu #251).

The positive controls are files the application saved on the guest while the
#251 probe ran: the plate holding an imported 20 mm STL, the same plate after
Reload from disk read a 30 mm file of the same name, and the plate saved after
the missing file's chooser was cancelled, with both STLs. Every negative
control is a copy of one of those files with one thing changed, or the wrong file.
"""
import copy
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests' / 'gui')]
from m7x_251_reload_from_disk import write_cube  # noqa: E402
from reload_oracle import (  # noqa: E402
    CLAUSE_MISSING, CLAUSE_RELOADED, clauses, explicit_missing_error, is_cube, verify_cube)

SAMPLES = ROOT / 'docs/runs/evidence/feishu-251-probe-2026-11-26/win11-test'
PREFIX = '7dc09061-'
MAIN = '3D/3dmodel.model'
SETTINGS = 'Metadata/model_settings.config'
SOURCE_KEY = "./object/part/metadata[@key='source_file']"
# The path the guest run gave the application; it exists on no other machine.
GUEST_SOURCE = r'C:\coil\orca-blackbox-v3-r1\artifacts\feishu-object-cases\251\run-qcs8j0pg\reload_cube.stl'
FILES = ('before-reload.3mf', 'after-reload.3mf', 'after-missing.3mf', 'source-20mm.stl', 'source-30mm.stl')


@pytest.fixture
def samples(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    for name in FILES:
        shutil.copyfile(SAMPLES / (PREFIX + name), run / name)
    return SimpleNamespace(before=run / 'before-reload.3mf', reloaded=run / 'after-reload.3mf',
                           after_missing=run / 'after-missing.3mf', stl20=run / 'source-20mm.stl',
                           stl30=run / 'source-30mm.stl', run=run)


def _rewrite(before, output, changes):
    """A copy of a saved project with the listed archive members replaced."""
    with ZipFile(before) as src, ZipFile(output, 'w') as dst:
        for info in src.infolist():
            dst.writestr(info, changes.get(info.filename, src.read(info.filename)))
    return output


def _settings(project, output, change):
    config = ET.fromstring(ZipFile(project).read(SETTINGS))
    change(config)
    return _rewrite(project, output, {SETTINGS: ET.tostring(config)})


def _doubled(project, output):
    """The same plate with a second, identical object 40 mm beside the first."""
    main = ET.fromstring(ZipFile(project).read(MAIN))
    core = main.tag.split('}')[0] + '}'
    resources, build = main.find(core + 'resources'), main.find(core + 'build')
    obj, = resources.findall(core + 'object')
    item, = build.findall(core + 'item')
    resources.append(_copy(obj, {'id': '3'}))
    build.append(_copy(item, {'objectid': '3', 'transform': item.get('transform').replace('100 100', '140 100')}))
    config = ET.fromstring(ZipFile(project).read(SETTINGS))
    row, = config.findall('object')
    plate, = config.findall('plate')
    config.insert(list(config).index(row) + 1, _copy(row, {'id': '3'}))
    plate.append(_copy(plate.find('model_instance')))
    plate.findall('model_instance')[-1].find("./metadata[@key='object_id']").set('value', '3')
    return _rewrite(project, output, {MAIN: ET.tostring(main), SETTINGS: ET.tostring(config)})


def _copy(node, attributes=None):
    clone = copy.deepcopy(node)
    for key, value in (attributes or {}).items():
        clone.set(key, value)
    return clone


def _placed(project, output, matrix):
    """The same project with its only instance turned by `matrix` (nine numbers) in place."""
    main = ET.fromstring(ZipFile(project).read(MAIN))
    item, = main.iter(main.tag.split('}')[0] + '}item')
    item.set('transform', ' '.join(map(str, (*matrix, *item.get('transform').split()[9:]))))
    return _rewrite(project, output, {MAIN: ET.tostring(main)})


def test_real_20mm_import_is_accepted(samples):
    reading = verify_cube(samples.before, samples.stl20, recorded=GUEST_SOURCE, side=20)
    assert reading == {'dimensions_mm': [20.0, 20.0, 20.0], 'triangles': 12, 'source_file': GUEST_SOURCE,
                       'same_source': True, 'object_names': ['reload_cube.stl'],
                       'placement_offset_mm': [90.0, 90.0, 0.0]}


def test_real_30mm_reload_is_accepted(samples):
    reading = verify_cube(samples.reloaded, samples.stl30, recorded=GUEST_SOURCE, side=30)
    assert reading['dimensions_mm'] == [30.0, 30.0, 30.0] and reading['triangles'] == 12
    assert reading['source_file'] == GUEST_SOURCE and reading['same_source']


def test_plate_after_the_cancelled_chooser_is_still_the_30mm_object(samples):
    reading = verify_cube(samples.after_missing, samples.stl30, recorded=GUEST_SOURCE, side=30)
    assert is_cube(reading, 30) and reading['object_names'] == ['reload_cube.stl']


def test_20mm_project_against_the_30mm_stl_is_rejected(samples):
    with pytest.raises(ValueError, match='reloaded mesh'):
        verify_cube(samples.before, samples.stl30, recorded=GUEST_SOURCE, side=30)


def test_30mm_project_against_the_20mm_stl_is_rejected(samples):
    with pytest.raises(ValueError, match='reloaded mesh'):
        verify_cube(samples.reloaded, samples.stl20, recorded=GUEST_SOURCE, side=30)
    with pytest.raises(ValueError, match='reloaded mesh'):
        verify_cube(samples.after_missing, samples.stl20, recorded=GUEST_SOURCE)


def test_wrong_span_is_rejected(samples):
    with pytest.raises(ValueError, match='30 mm on each axis, got \\[20\\.0, 20\\.0, 20\\.0\\]'):
        verify_cube(samples.before, samples.stl20, recorded=GUEST_SOURCE, side=30)


def test_two_objects_are_rejected(samples):
    doubled = _doubled(samples.before, samples.run / 'doubled.3mf')
    with pytest.raises(ValueError, match='exactly one object on the plate, found 2'):
        verify_cube(doubled, samples.stl20, recorded=GUEST_SOURCE, side=20)
    with pytest.raises(ValueError, match='exactly one object on the plate, found 2'):
        verify_cube(doubled, samples.stl30, recorded=GUEST_SOURCE, side=30)


def test_second_plate_is_rejected(samples):
    def second(config):
        plate, = config.findall('plate')
        config.insert(list(config).index(plate) + 1, copy.deepcopy(plate))
    with pytest.raises(ValueError, match='one plate'):
        verify_cube(_settings(samples.before, samples.run / 'two-plates.3mf', second),
                    samples.stl20, recorded=GUEST_SOURCE, side=20)


def test_cube_turned_by_90_degrees_is_rejected(samples):
    # The same eight corners at the same places: only the instance axes tell the turn.
    with pytest.raises(ValueError, match='instance axis'):
        verify_cube(_placed(samples.before, samples.run / 'turned.3mf', (0, 1, 0, -1, 0, 0, 0, 0, 1)),
                    samples.stl20, recorded=GUEST_SOURCE, side=20)


def test_another_source_file_is_rejected(samples, tmp_path):
    other = tmp_path / 'elsewhere' / 'reload_cube.stl'
    changed = _settings(samples.before, samples.run / 'other-source.3mf',
                        lambda config: config.find(SOURCE_KEY).set('value', str(other)))
    with pytest.raises(ValueError, match='names source file') as refused:
        verify_cube(changed, samples.stl20, side=20)
    # Both paths are named: the one the project holds and the one it should hold.
    assert str(other) in str(refused.value) and str(samples.stl20) in str(refused.value)


def test_the_guest_file_against_a_local_copy_is_rejected(samples):
    # The default asks for the path of the STL itself, which is not where the guest file was.
    with pytest.raises(ValueError, match='names source file') as refused:
        verify_cube(samples.before, samples.stl20, side=20)
    assert GUEST_SOURCE in str(refused.value) and str(samples.stl20) in str(refused.value)


def test_the_default_reads_the_path_of_the_stl_itself(samples):
    source = samples.run / 'reload_cube.stl'
    shutil.copyfile(samples.stl20, source)
    changed = _settings(samples.before, samples.run / 'local-source.3mf',
                        lambda config: config.find(SOURCE_KEY).set('value', str(source)))
    assert verify_cube(changed, source, side=20)['source_file'] == str(source)
    # The same path spelled with forward slashes and another case is still that path.
    other_spelling = _settings(changed, samples.run / 'spelled.3mf', lambda config: config.find(
        SOURCE_KEY).set('value', str(source).replace('\\', '/').upper()))
    assert verify_cube(other_spelling, source, side=20)['same_source']


def test_write_cube_still_writes_the_probe_files(samples, tmp_path):
    for size, sample in ((20, samples.stl20), (30, samples.stl30)):
        write_cube(tmp_path / f'cube{size}.stl', size)
        assert (tmp_path / f'cube{size}.stl').read_bytes() == sample.read_bytes()


@pytest.mark.parametrize('title,body', [
    ('Error', r'The file C:\dir\reload_cube.stl does not exist.'),
    ('Error', 'Source file not found!'),
    ('File not found', ''),
    ('Error', 'Missing file: reload_cube.stl'),
    ('Snapmaker Orca', 'reload_cube.stl is missing'),
    ('Error', 'The source has been deleted'),
])
def test_message_box_naming_a_missing_file_is_an_explicit_error(title, body):
    assert explicit_missing_error('message dialog', title, body)


@pytest.mark.parametrize('behavior,title,body', [
    # What the guest showed: a chooser asking for another file, with no message at all.
    ('replacement file chooser', 'Please select a file:', ''),
    # A chooser is never one, whatever its texts say.
    ('replacement file chooser', 'File not found', 'The file does not exist'),
    ('message dialog', 'Error', 'The object could not be reloaded.'),
    ('message dialog', 'Snapmaker Orca info', 'Failed to load the model.'),
    ('message dialog', 'Error', 'Cannot open file'),
    # "not found" belongs to another sentence than "file".
    ('message dialog', 'Error', 'See the log file for details. Error: not found'),
    ('message dialog', 'Reload', 'Please select a file to continue'),
    ('no dialog', '', ''),
    ('', '', ''),
])
def test_anything_else_is_not_an_explicit_error(behavior, title, body):
    assert not explicit_missing_error(behavior, title, body)


def test_clauses_follow_the_feishu_text(samples):
    before = verify_cube(samples.before, samples.stl20, recorded=GUEST_SOURCE, side=20)
    reloaded = verify_cube(samples.reloaded, samples.stl30, recorded=GUEST_SOURCE, side=30)
    assert (CLAUSE_RELOADED, CLAUSE_MISSING) == ('对象按磁盘最新文件重新加载，尺寸变为 30mm', '文件被删则明确报错')
    assert clauses(before, reloaded, 'message dialog', 'Error', 'File not found') == {
        CLAUSE_RELOADED: True, CLAUSE_MISSING: True}
    # The probe's own readings: the first clause holds, the second does not.
    assert clauses(before, reloaded, 'replacement file chooser', 'Please select a file:', '') == {
        CLAUSE_RELOADED: True, CLAUSE_MISSING: False}
    # An object that stayed 20 mm, a refused reading and a missing reading each fail the first clause.
    stayed = verify_cube(samples.before, samples.stl20, recorded=GUEST_SOURCE)
    for first, second in ((before, before), (before, stayed), ({'error': 'reloaded mesh: ...'}, reloaded),
                          ({}, {})):
        assert clauses(first, second, 'message dialog', 'Error', 'File not found')[CLAUSE_RELOADED] is False
    assert is_cube({'error': 'x'}, 30) is False and is_cube(stayed, 30) is False and is_cube(stayed, 20)
