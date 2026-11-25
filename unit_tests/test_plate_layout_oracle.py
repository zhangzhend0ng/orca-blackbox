from copy import deepcopy
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from harness.project_3mf import _CORE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from plate_layout_fixture import create_fixture
from plate_layout_oracle import verify_arrange, verify_clone, verify_orient


IDENTITY = '1 0 0 0 1 0 0 0 1'
FLAT = '0 0 1 0 1 0 -1 0 0'
YAW = '0 1 0 -1 0 0 0 0 1'


@pytest.fixture
def project(tmp_path):
    def make(case):
        path = tmp_path / f'before-{case}.3mf'
        create_fixture(ROOT / 'fixtures/feishu_std_cubesfar.3mf', path, case)
        return path
    return make


def _rewrite(before, output, transforms):
    with ZipFile(before) as src, ZipFile(output, 'w') as dst:
        main = ET.fromstring(src.read('3D/3dmodel.model'))
        settings = ET.fromstring(src.read('Metadata/model_settings.config'))
        build = main.find(_CORE + 'build')
        tasks = list(build)
        plate = settings.find('plate')
        first_instance = plate.find('model_instance')
        if len(tasks) == 1:
            for index in range(1, len(transforms)):
                item = deepcopy(tasks[0])
                build.append(item)
                tasks.append(item)
                instance = deepcopy(first_instance)
                instance.find("metadata[@key='instance_id']").set('value', str(index))
                plate.append(instance)
        for item, (rotation, x, y, z) in zip(tasks, transforms, strict=True):
            item.set('transform', f'{rotation} {x} {y} {z}')
        changes = {'3D/3dmodel.model': ET.tostring(main),
                   'Metadata/model_settings.config': ET.tostring(settings)}
        for name in src.namelist():
            dst.writestr(name, changes[name] if name in changes else src.read(name))
    return output


def test_arrange_rejects_separated_centres_that_still_overlap(project, tmp_path):
    before = project(240)
    solved = [(IDENTITY, 80, 140, 0), (IDENTITY, 130, 140, 0), (IDENTITY, 185, 140, 0)]
    after = _rewrite(before, tmp_path / 'arranged.3mf', solved)
    assert all(verify_arrange(before, after)['checks'].values())
    false_pass = _rewrite(before, tmp_path / 'centres-only.3mf',
                          [*solved[:2], (IDENTITY, 145, 140, 0)])
    report = verify_arrange(before, false_pass)
    assert report['checks']['every_pair_overlapped_before']
    assert not report['checks']['every_pair_disjoint_after']
    assert report['after_pairs'][-1] == {'objects': ['Bravo', 'Charlie'], 'overlap': True}
    out_of_bounds = _rewrite(before, tmp_path / 'outside.3mf',
                             [*solved[:2], (IDENTITY, 260, 140, 0)])
    report = verify_arrange(before, out_of_bounds)
    assert report['checks']['every_pair_disjoint_after']
    assert not report['checks']['all_inside_printable_bed_after']
    assert not verify_arrange(after, after)['checks']['every_pair_overlapped_before']


def test_orient_needs_improved_ground_contact_on_both_objects(project, tmp_path):
    before = project(241)
    solved = [(FLAT, 101, 132, 5.5), (FLAT, 197, 132, 7.5)]
    after = _rewrite(before, tmp_path / 'oriented.3mf', solved)
    report = verify_orient(before, after)
    assert all(report['checks'].values())
    assert report['objects']['Alpha']['tilt_deg'] == pytest.approx(90)
    assert report['objects']['Alpha']['after_contact_mm2'] == pytest.approx(55 * 33)
    assert report['objects']['Bravo']['after_contact_mm2'] == pytest.approx(62 * 39)
    wrong_direction = _rewrite(before, tmp_path / 'yaw-only.3mf',
                               [solved[0], (YAW, 176, 132, 0)])
    bad = verify_orient(before, wrong_direction)['checks']
    assert not bad['each_orientation_changed']
    assert not bad['each_contact_area_increased']
    lifted = _rewrite(before, tmp_path / 'floating.3mf', [solved[0], (FLAT, 197, 132, 9)])
    bad = verify_orient(before, lifted)['checks']
    assert bad['each_orientation_changed']
    assert not bad['each_contact_area_increased']
    assert not bad['each_grounded_and_in_printable_volume']


def test_clone_keeps_clone_and_fill_verdicts_independent(project, tmp_path):
    before = project(245)
    clone_positions = [(IDENTITY, 92, 135, 0), (IDENTITY, 175, 135, 0)]
    cloned = _rewrite(before, tmp_path / 'cloned.3mf', clone_positions)
    result = verify_clone(before, cloned)
    assert all(result['checks'][key] for key in list(result['checks'])[:4])
    assert not result['checks']['fill_saturation_verified']
    assert result['fill']['status'] == 'missing_saved_fill'
    overlap = _rewrite(before, tmp_path / 'overlap.3mf',
                       [clone_positions[0], (IDENTITY, 93, 135, 0)])
    wrong = verify_clone(before, overlap)['checks']
    assert wrong['copy_geometry_matches']
    assert not wrong['clone_is_separately_placed']
    sparse = _rewrite(before, tmp_path / 'sparse.3mf',
                      [*clone_positions, (IDENTITY, 92, 205, 0)])
    result = verify_clone(before, cloned, sparse)
    assert result['checks']['fill_adds_copies']
    assert result['checks']['fill_copies_nonoverlapping_and_in_bed']
    assert not result['checks']['fill_saturation_verified']
    grid = [(IDENTITY, x, y, 0) for x in (39, 103, 167, 231) for y in (40, 104, 168, 232)]
    filled = _rewrite(before, tmp_path / 'filled.3mf', grid)
    assert all(verify_clone(before, cloned, filled)['checks'].values())
