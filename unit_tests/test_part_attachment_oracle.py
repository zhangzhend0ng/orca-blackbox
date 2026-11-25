import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from harness.project_3mf import _CORE, _PROD


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from part_attachment_oracle import verify_attachment, verify_group_move


EVIDENCE = ROOT / 'docs/runs/evidence/feishu-250-251-2026-11-25/row-250-hyperv'
ORIGINAL = ROOT / 'fixtures/agent_layer_cube.3mf'
NEGATIVE = EVIDENCE / 'a7a65272-run2-negative-project.3mf'
STL = EVIDENCE / 'a7a65272-run2-cutter.stl'
MAIN = '3D/3dmodel.model'
SETTINGS = 'Metadata/model_settings.config'


def _rewrite(source, target, edit):
    with ZipFile(source) as archive, ZipFile(target, 'w') as out:
        members = {name: archive.read(name) for name in archive.namelist()}
        edit(members)
        for name, raw in members.items():
            out.writestr(name, raw)
    return target


@pytest.fixture
def attached(tmp_path):
    # Reclassify a harvested mesh to construct a controlled, synthetic attachment.
    def normal_part(members):
        members[SETTINGS] = members[SETTINGS].replace(b'negative_part', b'normal_part')

    return _rewrite(NEGATIVE, tmp_path / 'attached.3mf', normal_part)


def _move(members, x=10, move_parent=True, move_child=False):
    model = ET.fromstring(members[MAIN])
    if move_parent:
        _shift_x(model.find(_CORE + 'build/' + _CORE + 'item'), x)
    if move_child:
        _shift_x(model.findall('.//' + _CORE + 'component')[1], x)
    members[MAIN] = ET.tostring(model)


def _shift_x(node, dx):
    matrix = node.get('transform').split()
    matrix[9] = str(float(matrix[9]) + dx)
    node.set('transform', ' '.join(matrix))


def test_attachment_and_parent_move_reads_two_distinct_normal_parts(attached, tmp_path):
    moved = _rewrite(attached, tmp_path / 'moved.3mf', _move)
    attachment = verify_attachment(ORIGINAL, attached, STL)
    group = verify_group_move(attached, moved)

    assert attachment['printable_object_count'] == 1
    assert attachment['original']['triangle_count'] == attachment['attachment']['triangle_count'] == 12
    assert attachment['original']['world_bounds_mm'] != attachment['attachment']['world_bounds_mm']
    assert group['parent_delta_mm'] == (10.0, 0.0, 0.0)
    assert [p['delta_mm'] for p in group['parts']] == [(10.0, 0.0, 0.0)] * 2
    json.dumps([attachment, group], allow_nan=False)


def test_unchanged_original_and_unchanged_group_are_rejected(attached):
    with pytest.raises(ValueError, match='expected 2 uniquely identified parts'):
        verify_attachment(ORIGINAL, ORIGINAL, STL)
    with pytest.raises(ValueError, match='parent transform did not move'):
        verify_group_move(attached, attached)


def test_real_negative_part_is_rejected():
    with pytest.raises(ValueError, match='every part must be a normal_part'):
        verify_attachment(ORIGINAL, NEGATIVE, STL)


def test_wrong_geometry_with_same_bounds_is_rejected(attached, tmp_path):
    def change_triangle(members):
        model = ET.fromstring(members[MAIN])
        component = model.findall('.//' + _CORE + 'component')[1]
        name = component.get(_PROD + 'path').lstrip('/')
        component_model = ET.fromstring(members[name])
        mesh = next(obj for obj in component_model.findall('.//' + _CORE + 'object')
                    if obj.get('id') == component.get('objectid'))
        triangles = mesh.findall('.//' + _CORE + 'triangle')
        triangles[0].set('v3', triangles[1].get('v3'))
        members[name] = ET.tostring(component_model)

    wrong = _rewrite(attached, tmp_path / 'wrong.3mf', change_triangle)
    with pytest.raises(ValueError, match='facet geometry does not match'):
        verify_attachment(ORIGINAL, wrong, STL)


def test_second_build_item_is_rejected(attached, tmp_path):
    def extra_build_item(members):
        model = ET.fromstring(members[MAIN])
        build = model.find(_CORE + 'build')
        ET.SubElement(build, _CORE + 'item', {'objectid': build[0].get('objectid')})
        members[MAIN] = ET.tostring(model)

    separate = _rewrite(attached, tmp_path / 'separate.3mf', extra_build_item)
    with pytest.raises(ValueError, match='exactly one printable object'):
        verify_attachment(ORIGINAL, separate, STL)


@pytest.mark.parametrize('move_parent', [False, True])
def test_independent_child_movement_is_rejected(attached, tmp_path, move_parent):
    moved = _rewrite(attached, tmp_path / 'moved.3mf',
                     lambda members: _move(members, move_parent=move_parent, move_child=True))
    with pytest.raises(ValueError, match='parent transform did not move|local transform changed'):
        verify_group_move(attached, moved)
