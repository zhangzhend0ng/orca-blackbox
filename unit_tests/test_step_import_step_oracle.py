"""Controls for tests/step_import_oracle.py (Feishu #229).

The controls are the project the application saved for #227 (one imported
20 mm STL) with its geometry exchanged through zipfile for three cubes as
fixtures/assembly.step holds them: the mesh member, the build and the object
list of the model settings are rewritten, everything else stays as saved. The
three cubes are read as one object with three parts or as three objects. Every
negative control changes one thing, or hands over a record that says PASS.
"""
import copy
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests' / 'gui')]
from step_import_oracle import (  # noqa: E402
    CLAUSES, CLAUSE_COLOUR, CLAUSE_COMPLETE, CLAUSE_ENTITIES, CLAUSE_LIST, recorded_results_match,
    step_import_readings, verdicts, verify_step_import)
from m7x_229_import_step import (  # noqa: E402  (helpers of the case; none of these touches a window)
    SPLIT_OPTION, _tick_steps, assert_ticked, find_checkbox, notification_wparam, readings_of, run_tick_steps)

REAL_227 = ROOT / 'docs/runs/evidence/feishu-227-2026-11-26/11858f17-run1-imported.3mf'
MAIN, MESH = '3D/3dmodel.model', '3D/Objects/cube_20mm.stl_2.model'
SETTINGS, PROJECT = 'Metadata/model_settings.config', 'Metadata/project_settings.config'
CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PROD = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
PLACE = '1 0 0 0 1 0 0 0 1 135.5 136 10'  # where the application put the imported STL
COLOURS = ('#FF0000', '#0000FF', '#00C1AE')
NAMES = ('cube_red', 'cube_green', 'cube_blue')


def encode_state(state):
    """The paint value of an unsplit face painted with filament `state` (the bit layout of the 3MF writer)."""
    if state < 3:
        return format(state << 2, 'X')
    return format(state - 3, 'X') + 'C'


def _cube(x0, drop_last=False, extra=False):
    """The 12 triangles of a 10 mm cube with its corner at (x0, 0, 0); 11 of them, or 13 (a face
    repeated, which stands for a face the application divided)."""
    corners = ((x0, 0, 0), (x0 + 10, 0, 0), (x0 + 10, 10, 0), (x0, 10, 0),
               (x0, 0, 10), (x0 + 10, 0, 10), (x0 + 10, 10, 10), (x0, 10, 10))
    faces = ((0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
    triangles = [tuple(corners[index] for index in face) for face in faces]
    return triangles[:-1] if drop_last else triangles + triangles[:1] if extra else triangles


def _mesh(bodies):
    """The mesh member: one mesh object per (object id, triangles, paint filament or None)."""
    ET.register_namespace('', CORE[1:-1])
    model = ET.Element(CORE + 'model', {'unit': 'millimeter'})
    resources = ET.SubElement(model, CORE + 'resources')
    for object_id, triangles, paint in bodies:
        mesh = ET.SubElement(ET.SubElement(resources, CORE + 'object', {'id': object_id, 'type': 'model'}), CORE + 'mesh')
        vertices, faces = ET.SubElement(mesh, CORE + 'vertices'), ET.SubElement(mesh, CORE + 'triangles')
        index = {}
        for triangle in triangles:
            ids = []
            for corner in triangle:
                if corner not in index:
                    index[corner] = str(len(index))
                    ET.SubElement(vertices, CORE + 'vertex', dict(zip('xyz', (str(value) for value in corner))))
                ids.append(index[corner])
            attrs = dict(zip(('v1', 'v2', 'v3'), ids))
            if paint is not None:
                attrs['paint_color'] = encode_state(paint)
            ET.SubElement(faces, CORE + 'triangle', attrs)
    ET.SubElement(model, CORE + 'build')
    return ET.tostring(model, encoding='utf-8', xml_declaration=True)


def _main(groups):
    """3D/3dmodel.model: one object per group of mesh ids, each placed where the application placed the STL."""
    ET.register_namespace('', CORE[1:-1])
    ET.register_namespace('p', PROD[1:-1])
    model = ET.Element(CORE + 'model', {'unit': 'millimeter', 'requiredextensions': 'p'})
    resources, build = ET.SubElement(model, CORE + 'resources'), ET.SubElement(model, CORE + 'build')
    for object_id, mesh_ids in groups:
        components = ET.SubElement(ET.SubElement(resources, CORE + 'object', {'id': object_id, 'type': 'model'}),
                                   CORE + 'components')
        for mesh_id in mesh_ids:
            ET.SubElement(components, CORE + 'component',
                          {PROD + 'path': '/' + MESH, 'objectid': mesh_id, 'transform': '1 0 0 0 1 0 0 0 1 0 0 0'})
        ET.SubElement(build, CORE + 'item', {'objectid': object_id, 'transform': PLACE, 'printable': '1'})
    return ET.tostring(model, encoding='utf-8', xml_declaration=True)


def _metadata(key, value):
    return ET.Element('metadata', {'key': key, 'value': value})


def _settings(raw, rows):
    """The real model settings with its objects and plate instances replaced by
    `rows`: [(object id, object name, [(part id, part name, extruder or None)])]."""
    root = ET.fromstring(raw)
    plate = root.find('plate')
    for node in root.findall('object'):
        root.remove(node)
    for node in plate.findall('model_instance'):
        plate.remove(node)
    for index, (object_id, name, parts) in enumerate(rows):
        obj = ET.Element('object', {'id': object_id})
        obj.append(_metadata('name', name))
        for part_id, part_name, extruder in parts:
            part = ET.SubElement(obj, 'part', {'id': part_id, 'subtype': 'normal_part'})
            part.append(_metadata('name', part_name))
            if extruder is not None:
                part.append(_metadata('extruder', str(extruder)))
        root.insert(index, obj)
        instance = ET.SubElement(plate, 'model_instance')
        instance.append(_metadata('object_id', object_id))
        instance.append(_metadata('instance_id', '0'))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def step_project(target, layout='parts', cubes=(0, 20, 40), extruders=(1, 2, 3), colours=COLOURS,
                 names=NAMES, paint=None, drop_last_of=None, extra_of=()):
    """The real #227 project holding one cube per entry of `cubes`: as one object with a part for
    each (``parts``) or as an object for each (``objects``). Each part gets its extruder, or, with
    `paint`, is painted with that filament."""
    bodies = [(str(1 + 2 * index), _cube(x0, drop_last_of == index, index in extra_of),
               paint[index] if paint else None) for index, x0 in enumerate(cubes)]
    mesh_ids = [body[0] for body in bodies]
    parts = [(body[0], f'{names[index]}_part', None if paint else extruders[index]) for index, body in enumerate(bodies)]
    if layout == 'parts':
        groups, rows = [('2', mesh_ids)], [('2', 'assembly', parts)]
    else:
        groups = [(str(2 + 3 * index), [body[0]]) for index, body in enumerate(bodies)]
        rows = [(str(2 + 3 * index), names[index], [parts[index]]) for index in range(len(bodies))]
    with ZipFile(REAL_227) as src:
        old = {name: src.read(name) for name in (SETTINGS, PROJECT)}
        settings = json.loads(old[PROJECT])
        settings['filament_colour'][:len(colours)] = list(colours)
        with ZipFile(target, 'w', ZIP_DEFLATED) as dst:
            for info in src.infolist():
                replaced = {MESH: _mesh(bodies), MAIN: _main(groups), SETTINGS: _settings(old[SETTINGS], rows),
                            PROJECT: json.dumps(settings).encode('utf-8')}
                dst.writestr(info.filename, replaced.get(info.filename, src.read(info.filename)))
    return Path(target)


def _words(*names):
    return [(name, 10, 10 * index, 60, 12) for index, name in enumerate(names)]


@pytest.mark.parametrize('layout', ['parts', 'objects'])
def test_three_cubes_in_three_filaments_pass(tmp_path, layout):
    project = step_project(tmp_path / f'{layout}.3mf', layout)
    readings = verify_step_import(project, _words(*(NAMES if layout == 'objects' else ('assembly',))))
    assert all(readings['checks'].values())
    assert readings['entity_count'] == 3 and readings['triangle_counts'] == [12, 12, 12] and readings['triangles_total'] == 36
    assert [entity['filament'] for entity in readings['entities']] == [1, 2, 3] and readings['side_by_side']
    assert all(round(entity['box_volume_mm3'], 6) == 1000.0 for entity in readings['entities'])
    assert readings['object_names'] == (list(NAMES) if layout == 'objects' else ['assembly'])
    assert verdicts(readings) == dict.fromkeys(CLAUSES, 'PASS')
    assert recorded_results_match({'case': 229, 'results': dict.fromkeys(CLAUSES, 'PASS')}, readings)


def test_colours_kept_as_paint_on_the_faces_pass(tmp_path):
    """The three parts share extruder 1 and carry their colour as paint on every face."""
    project = step_project(tmp_path / 'painted.3mf', paint=(1, 2, 3))
    readings = verify_step_import(project, _words('assembly'))
    assert [entity['filament'] for entity in readings['entities']] == [1, 2, 3]
    assert [entity['faces_without_paint'] for entity in readings['entities']] == [0, 0, 0]


def test_faces_divided_alike_pass(tmp_path):
    """One face repeated on every cube (13 triangles each): divided alike is not a missing piece."""
    project = step_project(tmp_path / 'divided.3mf', extra_of=(0, 1, 2))
    readings = step_import_readings(project, _words('assembly'))
    assert readings['triangle_counts'] == [13, 13, 13] and readings['checks'][CLAUSE_COMPLETE]


def test_faces_divided_differently_are_refused(tmp_path):
    readings = _fails(tmp_path, 'uneven', CLAUSE_COMPLETE, extra_of=(1,))
    assert readings['triangle_counts'] == [12, 13, 12] and readings['checks'][CLAUSE_ENTITIES]


def _fails(tmp_path, name, clause, **options):
    words = _words(*options.pop('words', NAMES if options.get('layout') == 'objects' else ('assembly',)))
    project = step_project(tmp_path / f'{name}.3mf', **options)
    readings = step_import_readings(project, words)
    assert not readings['checks'][clause]
    with pytest.raises(ValueError, match=clause):
        verify_step_import(project, words)
    assert not recorded_results_match({'case': 229, 'results': dict.fromkeys(CLAUSES, 'PASS')}, readings)
    return readings


def test_two_cubes_are_refused(tmp_path):
    readings = _fails(tmp_path, 'two', CLAUSE_ENTITIES, cubes=(0, 20), extruders=(1, 2), colours=COLOURS[:2],
                      names=NAMES[:2])
    assert readings['entity_count'] == 2


def test_four_cubes_are_refused(tmp_path):
    four = (0, 20, 40, 60)
    readings = _fails(tmp_path, 'four', CLAUSE_ENTITIES, cubes=four, extruders=(1, 2, 3, 4), colours=COLOURS + ('#123456',),
                      names=NAMES + ('cube_black',))
    assert readings['entity_count'] == 4 and not readings['checks'][CLAUSE_COMPLETE]


def test_three_cubes_in_one_filament_are_refused(tmp_path):
    readings = _fails(tmp_path, 'same', CLAUSE_COLOUR, extruders=(1, 1, 1))
    assert [entity['filament'] for entity in readings['entities']] == [1, 1, 1]


def test_three_filaments_of_one_colour_are_refused(tmp_path):
    readings = _fails(tmp_path, 'grey', CLAUSE_COLOUR, colours=('#FF0000',) * 3)
    assert [entity['filament'] for entity in readings['entities']] == [1, 2, 3]


def test_cubes_merged_into_one_part_are_refused(tmp_path):
    """One part holding all 36 triangles: a single entity, whatever was there in the STEP."""
    target = tmp_path / 'merged.3mf'
    step_project(target)
    with ZipFile(target) as src, ZipFile(tmp_path / 'one.3mf', 'w', ZIP_DEFLATED) as dst:
        for info in src.infolist():
            raw = src.read(info.filename)
            if info.filename == MESH:
                raw = _mesh([('1', _cube(0) + _cube(20) + _cube(40), None)])
            elif info.filename == MAIN:
                raw = _main([('2', ['1'])])
            elif info.filename == SETTINGS:
                raw = _settings(raw, [('2', 'assembly', [('1', 'one_part', 1)])])
            dst.writestr(info.filename, raw)
    readings = step_import_readings(tmp_path / 'one.3mf', _words('assembly'))
    assert readings['entity_count'] == 1 and readings['triangles_total'] == 36
    assert not any(readings['checks'].values())


def test_a_cube_with_eleven_faces_is_refused(tmp_path):
    readings = _fails(tmp_path, 'eleven', CLAUSE_COMPLETE, drop_last_of=1)
    assert readings['triangle_counts'] == [12, 11, 12] and readings['checks'][CLAUSE_ENTITIES]


def test_a_name_missing_from_the_object_list_is_refused(tmp_path):
    project = step_project(tmp_path / 'objects.3mf', 'objects')
    with pytest.raises(ValueError, match=CLAUSE_LIST):
        verify_step_import(project, _words('cube_red', 'cube_blue', 'something_else'))
    assert step_import_readings(project, _words('cube_red', 'cube_green', 'cube_b1ue'))['checks'][CLAUSE_LIST], \
        'one misread character is tolerated'


def test_a_record_that_says_pass_is_not_taken_at_its_word(tmp_path):
    readings = step_import_readings(step_project(tmp_path / 'same.3mf', extruders=(1, 1, 1)), _words('assembly'))
    flat = {'case': 229, 'results': dict.fromkeys(CLAUSES, 'PASS')}
    assert not recorded_results_match(flat, readings)
    assert recorded_results_match({'case': 229, 'results': verdicts(readings)}, readings)
    good = step_import_readings(step_project(tmp_path / 'good.3mf'), _words('assembly'))
    assert recorded_results_match({'case': 229, 'results': dict.fromkeys(CLAUSES, 'PASS')}, good)
    assert not recorded_results_match({'case': 228, 'results': dict.fromkeys(CLAUSES, 'PASS')}, good)
    assert not recorded_results_match({'case': 229}, good)


def _rewrite(source, target, replaced):
    """Copy a saved 3MF with some members replaced."""
    with ZipFile(source) as src, ZipFile(target, 'w', ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info.filename, replaced.get(info.filename, src.read(info.filename)))


def unticked_project(target):
    """What the application saved on the first guest run (dev229a-253195c), with the "Split
    compound and compsolid into multiple objects" box left as it comes: one object named after
    the file, one part holding the 36 triangles of the three cubes, no extruder of its own."""
    step_project(target)
    with ZipFile(target) as src:
        settings = json.loads(src.read(PROJECT))
    settings['filament_colour'][0] = '#FF0000'
    _rewrite(target, target.with_name('unticked.3mf'), {
        MESH: _mesh([('1', _cube(0) + _cube(20) + _cube(40), None)]), MAIN: _main([('2', ['1'])]),
        SETTINGS: _settings(_settings_xml(target), [('2', 'assembly.step', [('1', 'assembly', None)])]),
        PROJECT: json.dumps(settings).encode('utf-8')})
    return target.with_name('unticked.3mf')


def _settings_xml(path):
    with ZipFile(path) as archive:
        return archive.read(SETTINGS)


def test_option_unticked_one_part_of_36_faces_fails_every_clause(tmp_path):
    """The first guest run, read back: 1 entity of 36 triangles in the first filament."""
    project = unticked_project(tmp_path / 'as-unticked.3mf')
    readings = step_import_readings(project, _words('assembly.step'))
    assert verdicts(readings) == {
        CLAUSE_ENTITIES: 'FAIL (1 entities, boxes [5000.0] mm3)',
        CLAUSE_LIST: 'FAIL (object names [\'assembly.step\'], read [\'assembly.step\'])',
        CLAUSE_COLOUR: "FAIL (filaments [1], colours {'1': '#ff0000'})",
        CLAUSE_COMPLETE: 'FAIL (1 个实体，36 个三角面：三个立方体并成了一个部件)'}
    assert not recorded_results_match({'case': 229, 'results': dict.fromkeys(CLAUSES, 'PASS')}, readings)
    assert not any(readings['checks'].values()) and readings['triangles_total'] == 36 and not readings['side_by_side']


# The census of "Step file import parameters" as the first guest run surveyed it (run
# dev229a-253195c): (class, text, rectangle). Handles are left out on purpose.
CENSUS = [
    ('Static', 'Smaller linear and angular deflections result in higher-quality\ntransformations but increase the processing time.', [788, 442, 1109, 473]),
    ('Static', 'View Wiki for more information', [788, 473, 964, 490]),
    ('Static', 'Linear Deflection: ', [788, 510, 883, 526]),
    ('msctls_trackbar32', '', [888, 510, 1088, 535]),
    ('wxWindowNR', '', [1093, 510, 1163, 536]),
    ('Edit', '0.003', [1098, 514, 1153, 532]),
    ('Static', 'Angle Deflection: ', [788, 542, 882, 558]),
    ('msctls_trackbar32', '', [888, 542, 1088, 567]),
    ('wxWindowNR', '', [1093, 542, 1163, 568]),
    ('Edit', '0.50', [1098, 546, 1153, 564]),
    ('Button', SPLIT_OPTION, [788, 594, 1089, 609]),
    ('Static', 'Number of triangular facets: ', [788, 646, 940, 662]),
    ('Static', '36', [940, 646, 1090, 662]),
    ('Button', "Don't show again", [788, 716, 902, 731]),
    ('wxWindowNR', 'panel', [963, 698, 1183, 750]),
    ('wxWindowNR', 'OK', [963, 708, 1063, 740]),
    ('wxWindowNR', 'Cancel', [1073, 708, 1173, 740]),
]


def _children(census):
    return [{'class': cls, 'text': text, 'rect': rect, 'hwnd': 1000 + index, 'id': -30000 + index,
             'enabled': True, 'visible': True} for index, (cls, text, rect) in enumerate(census)]


def test_the_split_box_is_found_among_the_dialog_windows():
    children = _children(CENSUS)
    split = find_checkbox(children, SPLIT_OPTION)
    assert split['class'] == 'Button' and split['rect'] == [788, 594, 1089, 609]
    assert find_checkbox(children, "Don't show again")['rect'] == [788, 716, 902, 731]
    assert find_checkbox(children, 'OK') is None, 'OK is a drawn button, not a check box'
    assert find_checkbox(children, 'Split compound') is None, 'the whole text is what counts'
    assert find_checkbox(children[:10], SPLIT_OPTION) is None
    assert find_checkbox(children + [dict(split, hwnd=9999)], SPLIT_OPTION) is None, 'two of them: none is taken'


def test_the_dialog_readings_are_the_deflections_and_the_facet_count():
    assert readings_of(_children(CENSUS)) == {'linear_deflection': '0.003', 'angle_deflection': '0.50',
                                              'triangular_facets': '36'}
    assert readings_of([]) == {'linear_deflection': None, 'angle_deflection': None, 'triangular_facets': None}


class _Box:
    """A check box for run_tick_steps without a window: read() tells its state and each step sets
    the next state given here (or, given a note, leaves the state alone)."""

    def __init__(self, start, *after):
        self.state, self.after, self.run = start, list(after), []

    def read(self):
        return self.state

    def step(self, how, note=None):
        def act(_record):
            self.run.append(how)
            return note if note else self._set()
        return how, act

    def _set(self):
        self.state = self.after.pop(0)


FIRST, SECOND, THIRD = 'first way', 'second way', 'third way'


def _steps(box):
    return [box.step(FIRST), box.step(SECOND), box.step(THIRD)]


def test_the_first_way_that_ticks_the_box_ends_the_run():
    box = _Box(0, 1, 0, 0)
    records, state = run_tick_steps(box.read, _steps(box))
    assert state == 1 and [record['how'] for record in records] == [FIRST]
    assert records[0] == {'how': FIRST, 'before': 0, 'after': 1} and box.run == [FIRST]
    assert_ticked(records, state)


def test_a_box_that_still_reads_zero_is_given_the_next_way():
    box = _Box(0, 0, 1, 0)
    records, state = run_tick_steps(box.read, _steps(box))
    assert state == 1 and [record['how'] for record in records] == [FIRST, SECOND]
    assert [(record['before'], record['after']) for record in records] == [(0, 0), (0, 1)]
    box = _Box(0, 0, 0, 1)
    records, state = run_tick_steps(box.read, _steps(box))
    assert state == 1 and len(records) == 3 and records[-1]['after'] == 1


def test_a_box_that_is_ticked_already_is_left_alone():
    box = _Box(1)
    records, state = run_tick_steps(box.read, _steps(box))
    assert state == 1 and records == [] and box.run == []


def test_a_step_that_is_skipped_is_recorded_and_the_next_one_is_tried():
    box = _Box(0, 1)
    records, state = run_tick_steps(box.read, [box.step(SECOND, note='skipped: another window covers the box'),
                                               box.step(THIRD)])
    assert state == 1 and [record['how'] for record in records] == [SECOND, THIRD]
    assert records[0] == {'how': SECOND, 'before': 0, 'after': 0, 'note': 'skipped: another window covers the box'}


def test_three_ways_that_do_not_tick_the_box_raise_naming_each():
    box = _Box(0, 0, 0, 0)
    records, state = run_tick_steps(box.read, _steps(box))
    assert state == 0 and len(records) == 3 and box.run == [FIRST, SECOND, THIRD]
    with pytest.raises(ValueError, match='reads 0 after 3 step') as caught:
        assert_ticked(records, state)
    for how in (FIRST, SECOND, THIRD):
        assert f'{how}: 0 -> 0' in str(caught.value)


def test_the_three_ways_are_the_prescribed_ones_in_order():
    ways = [how for how, _act in _tick_steps(None, 0, {'hwnd': 0, 'id': -30284, 'rect': [788, 594, 1089, 609]})]
    assert ways == ['BM_CLICK sent to the check box',
                    'dialog brought to the foreground, real click on the box',
                    'BM_SETCHECK, then WM_COMMAND BN_CLICKED sent to the dialog']


def test_the_notification_carries_the_control_id_and_bn_clicked():
    wparam = notification_wparam(-30284)
    # A negative control id is a 16-bit id: its low word, and nothing in the high word.
    assert 0 <= wparam <= 0xFFFF and wparam == 65536 - 30284 == (-30284 & 0xFFFF) and wparam >> 16 == 0
    assert notification_wparam(5100) == 5100
