"""Offline checks for Feishu #229: a STEP file of three coloured solids imported through File > Import.

Every function here reads what the application put on disk, or the words the
object list showed; nothing drives the GUI. ``step_import_readings`` never
raises for a failed expectation: it returns its readings with ``checks``, one
for each clause of the Feishu expectation. ``verify_step_import`` raises
ValueError on the first failed clause. ``recorded_results_match`` holds what a
run recorded against what the files say.

The fixture is fixtures/assembly.step (tools/make_assembly_step.py): three
10 mm cubes side by side along x, 10 mm apart, each resting on z = 0, each
with its own colour. Whether the application loads it as one object with
three parts or as three objects is not known beforehand, so an "entity" here
is a part of the saved project (a ``<part>`` of ``Metadata/model_settings.config``
with its mesh), whatever object it belongs to; three one-part objects and one
three-part object read the same.

How each clause is read:

* ``3 个实体均被导入``: exactly three entities, and each one's box holds
  1000 mm3 within 1 mm3. A cube of planar faces keeps its corners through the
  STEP reader and the tessellation, and the application writes coordinates
  with far more than three decimals; an error of 0.001 mm on every coordinate
  of a 10 mm cube moves its box volume by at most 0.3 mm3, so 1 mm3 is a
  bound on rounding and nothing else.
* ``对象列表可见对应零件（或拆分为多对象）``: the project holds three
  entities in at least one object, and every object name it holds is read in
  the object list once (``import_stl_oracle.listed_object_names``: a
  misread character is tolerated).
* ``颜色保留``: each entity prints with one filament of its own (a face with
  its paint, a face without with its part's extruder), the three filaments
  differ, and their colours in ``filament_colour`` differ. That covers a
  colour kept as paint on the triangles and one kept as an extruder.
* ``无缺件``: exactly three entities, none missing and none merged into
  another; each has the 12 triangles of a cube, or, when the application
  divided them, as many as its two neighbours and at least 12. One part of
  the 36 triangles of the three cubes is what the application saved when its
  "Split compound and compsolid into multiple objects" box was left as it
  comes (run dev229a-253195c), and the verdict says so in those words.
"""
from pathlib import Path

from colored_obj_oracle import DEFAULT_EXTRUDER, _colour, _extents, _prints_with, read_colored_project
from import_stl_oracle import listed_object_names

CLAUSE_ENTITIES = '3 个实体均被导入'
CLAUSE_LIST = '对象列表可见对应零件（或拆分为多对象）'
CLAUSE_COLOUR = '颜色保留'
CLAUSE_COMPLETE = '无缺件'
CLAUSES = (CLAUSE_ENTITIES, CLAUSE_LIST, CLAUSE_COLOUR, CLAUSE_COMPLETE)
CUBE_MM = 10.0
CUBE_VOLUME_MM3 = CUBE_MM ** 3
VOLUME_TOL_MM3 = 1.0  # 0.001 mm on every coordinate of a 10 mm cube moves its box volume by at most 0.3 mm3
FACES_PER_CUBE = 12
ENTITIES = 3


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _entity(entry, part):
    """What one part of a saved project is: its box, its faces, and the filaments they print with."""
    corners = [corner for face in part['faces'] for corner in face['corners']]
    box = _extents(corners)
    base = next((value for value in (part['extruder'], entry['extruder']) if value), DEFAULT_EXTRUDER)
    filaments = sorted({_prints_with(face, base) for face in part['faces']} - {None}, key=str)
    return {'object': entry['name'], 'part': part['name'], 'subtype': part['subtype'], 'triangles': len(part['faces']),
            'box_mm': [[round(value, 6) for value in pair] for pair in box] if corners else None,
            'box_volume_mm3': (box[0][1] - box[0][0]) * (box[1][1] - box[1][0]) * (box[2][1] - box[2][0]) if corners else 0.0,
            'extruder': part['extruder'], 'object_extruder': entry['extruder'],
            'faces_without_paint': sum(1 for face in part['faces'] if not face['paint']),
            'filaments': filaments,
            'filament': filaments[0] if len(filaments) == 1 and all(_prints_with(face, base) is not None for face in part['faces'])
            else None}


def _side_by_side(entities):
    """Whether the boxes are the fixture's: the same y and z range, 10 mm wide, 20 mm from one to the next."""
    boxes = sorted((entity['box_mm'] for entity in entities), key=lambda box: box[0][0])
    if len(boxes) != ENTITIES or any(entity['box_mm'] is None for entity in entities):
        return False
    same_yz = all(abs(box[axis][0] - boxes[0][axis][0]) <= 1e-6 and abs(box[axis][1] - boxes[0][axis][1]) <= 1e-6
                  for box in boxes for axis in (1, 2))
    return (same_yz and all(abs(box[0][1] - box[0][0] - CUBE_MM) <= 1e-6 for box in boxes)
            and all(abs(later[0][0] - earlier[0][0] - 2 * CUBE_MM) <= 1e-6 for earlier, later in zip(boxes, boxes[1:])))


def step_import_readings(project, object_words):
    """Feishu #229: what the saved project holds and what the object list showed, with one check
    per clause. `object_words` are the OCR words of the object list as
    ``ocr_words_img`` gives them (the text first). ``error`` is set when the project cannot be read."""
    try:
        saved = read_colored_project(Path(project))
        entities = [_entity(entry, part) for entry in saved['objects'] for part in entry['volumes']]
    except (OSError, ValueError) as exc:
        return {'checks': dict.fromkeys(CLAUSES, False), 'error': str(exc)}
    colours = saved['filament_colour']
    named = []
    try:
        named = listed_object_names(object_words, saved['object_names'])
        listed = True
    except ValueError:
        listed = False
    filaments = [entity['filament'] for entity in entities]
    one_each = (len(entities) == ENTITIES and None not in filaments
                and len(set(filaments)) == ENTITIES and len({_colour(colours, value) for value in filaments}) == ENTITIES)
    counts = [entity['triangles'] for entity in entities]
    checks = {
        CLAUSE_ENTITIES: len(entities) == ENTITIES and all(
            abs(entity['box_volume_mm3'] - CUBE_VOLUME_MM3) <= VOLUME_TOL_MM3 for entity in entities),
        CLAUSE_LIST: listed and len(saved['object_names']) >= 1 and len(entities) == ENTITIES,
        CLAUSE_COLOUR: one_each,
        CLAUSE_COMPLETE: len(entities) == ENTITIES and (
            all(count == FACES_PER_CUBE for count in counts)
            or all(count >= FACES_PER_CUBE for count in counts) and len(set(counts)) == 1),
    }
    return {'checks': checks, 'object_names': saved['object_names'], 'entities': entities,
            'entity_count': len(entities), 'triangles_total': sum(counts), 'triangle_counts': counts,
            'filament': dict(zip((entity['part'] or '' for entity in entities), filaments)),
            'filament_colours': {str(entity['filament']): _colour(colours, entity['filament']) for entity in entities},
            'filament_colour': colours, 'printer': saved['printer'],
            'triangle_attribute_names': saved['triangle_attribute_names'],
            'side_by_side': _side_by_side(entities),
            'object_list': {'names': saved['object_names'], 'found': named, 'listed': listed,
                            'words': [str(word[0]) for word in object_words][:400]}}


def _why(readings, clause):
    if 'error' in readings:
        return readings['error']
    if clause == CLAUSE_ENTITIES:
        return (f'{readings["entity_count"]} entities, boxes '
                f'{[round(entity["box_volume_mm3"], 3) for entity in readings["entities"]]} mm3')
    if clause == CLAUSE_LIST:
        return f'object names {readings["object_names"]}, read {readings["object_list"]["found"]}'
    if clause == CLAUSE_COLOUR:
        return f'filaments {[entity["filament"] for entity in readings["entities"]]}, colours {readings["filament_colours"]}'
    if len(readings['entities']) == 1 and readings['triangles_total'] == ENTITIES * FACES_PER_CUBE:
        return f'1 个实体，{ENTITIES * FACES_PER_CUBE} 个三角面：三个立方体并成了一个部件'
    return f'triangle counts {readings["triangle_counts"]}'


def verdicts(readings):
    """{clause of the Feishu expectation: 'PASS' or 'FAIL (what was read)'}."""
    return {clause: 'PASS' if readings['checks'].get(clause) else f'FAIL ({_why(readings, clause)})'
            for clause in CLAUSES}


def verify_step_import(project, object_words):
    """Raises ValueError naming the first failed clause; returns the readings."""
    readings = step_import_readings(project, object_words)
    if 'error' in readings:
        raise ValueError(readings['error'])
    for clause in CLAUSES:
        if not readings['checks'][clause]:
            raise ValueError(f'{Path(project).name}: {clause}: {_why(readings, clause)}')
    return readings


def recorded_results_match(analysis, readings):
    """Whether what a run recorded is what its files say: the case number and, clause for clause,
    the verdicts recomputed from the readings. A record that says PASS where the files do not
    agrees with nothing."""
    recorded = analysis.get('results') if isinstance(analysis, dict) else None
    return analysis.get('case') == 229 and isinstance(recorded, dict) and recorded == verdicts(readings)
