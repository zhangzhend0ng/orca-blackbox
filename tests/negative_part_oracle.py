"""Independent archive and extrusion geometry checks for the #250 cube."""

import math
import re
from statistics import median

from harness.project_3mf import _CORE, _PROD, _apply, _archive, _numbers, _xml


def project_boxes(path):
    files = _archive(path.read_bytes(), lambda: False)
    models = {name: _xml(data) for name, data in files.items() if name.endswith('.model')}
    model = models['3D/3dmodel.model']
    (item,) = model.findall(_CORE + 'build/' + _CORE + 'item')
    assert item.get('printable', '1') == '1'
    transform = _numbers(item.get('transform'), 12)
    (body,) = [obj for obj in model.findall(_CORE + 'resources/' + _CORE + 'object')
               if obj.get('id') == item.get('objectid')]
    config = _xml(files['Metadata/model_settings.config'])
    (obj_config,) = config.findall('object')
    assert obj_config.get('id') == body.get('id')
    assert len(config.findall('plate/model_instance')) == 1
    parts = {part.get('id'): part.get('subtype') for part in obj_config.findall('part')}
    boxes = {}
    for component in body.findall(_CORE + 'components/' + _CORE + 'component'):
        offset = _numbers(component.get('transform'), 12)
        part_id = component.get('objectid')
        part_file = component.get(_PROD + 'path').lstrip('/')
        (part,) = [obj for obj in models[part_file].findall(_CORE + 'resources/' + _CORE + 'object')
                   if obj.get('id') == part_id]
        vertices = part.findall(_CORE + 'mesh/' + _CORE + 'vertices/' + _CORE + 'vertex')
        assert len(vertices) == 8, 'expected a cuboid mesh'
        world = [_apply(transform, _apply(offset, _numbers(' '.join(v.get(k) for k in 'xyz'), 3)))
                 for v in vertices]
        kind = parts[part_id]
        assert kind not in boxes, f'duplicate volume type: {kind}'
        boxes[kind] = [[float(min(axis)), float(max(axis))] for axis in zip(*world)]
    assert len(boxes) == len(parts)
    return boxes


def _segments(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    start, end = lines.index('; EXECUTABLE_BLOCK_START'), lines.index('; EXECUTABLE_BLOCK_END')
    assert start < end
    position = dict.fromkeys('XYZE')
    xyz_absolute, e_relative, active = None, None, None
    label = re.compile(r'; (printing|stop printing) object (.+) id:\d+ copy \d+$')
    names = set()
    for line in lines[start + 1:end]:
        match = label.fullmatch(line)
        if match:
            direction, name = match.groups()
            if direction == 'printing':
                assert active is None
                active = name
                names.add(name)
            else:
                assert active == name
                active = None
            continue
        code = line.partition(';')[0].strip()
        if not code:
            continue
        if code.startswith('EXCLUDE_OBJECT_START NAME='):
            assert active is None
            active = code.split('NAME=', 1)[1]
            names.add(active)
            continue
        if code.startswith('EXCLUDE_OBJECT_END NAME='):
            assert active is not None and code.split('NAME=', 1)[1] == active
            active = None
            continue
        op, *args = code.split()
        if op in ('G90', 'G91'):
            xyz_absolute = op == 'G90'
        elif op in ('M82', 'M83'):
            e_relative = op == 'M83'
        elif op == 'G28':
            assert active is None
            position = dict.fromkeys('XYZE')
        elif op in ('G0', 'G1', 'G2', 'G3', 'G92'):
            values = {word[0]: float(word[1:]) for word in args if word[0] in 'XYZE'}
            if op == 'G92':
                assert active is None or values.keys() <= {'E'}
                position.update(values)
                continue
            old = position.copy()
            for axis in 'XYZ':
                if axis in values:
                    assert xyz_absolute is not None
                    position[axis] = values[axis] if xyz_absolute else old[axis] + values[axis]
            amount = 0.0
            if 'E' in values:
                assert e_relative is not None
                amount = values['E'] if e_relative else values['E'] - (old['E'] or 0.0)
                position['E'] = values['E']
            if op in ('G2', 'G3'):
                assert active is None or amount <= 0, 'extruding arc cannot be compared as a line'
                for axis in 'XYZ':
                    if axis not in values:
                        continue
                    position[axis] = values[axis] if xyz_absolute else position[axis]
            elif active is not None and amount > 0 and any(old[k] != position[k] for k in 'XY'):
                assert old['Z'] == position['Z'] and all(old[k] is not None and position[k] is not None for k in 'XYZ')
                yield tuple(old[k] for k in 'XYZ'), tuple(position[k] for k in 'XYZ')
    assert active is None and len(names) == 1, f'expected one object in positive extrusion, found {names}'


def _overlap_length(a, b, bounds):
    if not bounds[2][0] <= a[2] <= bounds[2][1]:
        return 0.0
    low, high = 0.0, 1.0
    for x, y, (left, right) in zip(a[:2], b[:2], bounds[:2]):
        delta = y - x
        if delta == 0:
            if not left <= x <= right:
                return 0.0
            continue
        first, last = sorted(((left - x) / delta, (right - x) / delta))
        low, high = max(low, first), min(high, last)
    return max(0.0, high - low) * math.dist(a[:2], b[:2])


def measure_difference(baseline, negative, body, cutter):
    overlap = [[max(a, c), min(b, d)] for (a, b), (c, d) in zip(body, cutter)]
    assert all(b - a > 4 for a, b in overlap), f'cutter does not overlap the solid: {overlap}'
    assert any(a < x or b > y for (a, b), (x, y) in zip(cutter[:2], body[:2]))
    # Pull the witness in from the new cavity wall and skip top/bottom layers.
    removed = [[a + 1.5, b - 1.5] for a, b in overlap]
    retained = [[body[i][0] + body[i][1] - hi, body[i][0] + body[i][1] - lo]
                for i, (lo, hi) in enumerate(removed[:2])] + [removed[2]]
    assert any(b < c or d < a for (a, b), (c, d) in zip(removed[:2], retained[:2]))

    def evidence(path):
        segments = list(_segments(path))
        assert segments
        return {'removed_region_mm': sum(_overlap_length(a, b, removed) for a, b in segments),
                'retained_region_mm': sum(_overlap_length(a, b, retained) for a, b in segments),
                'layer_count': len({a[2] for a, _ in segments}),
                'body_center_z': median(a[2] for a, _ in segments),
                'object_extruding_segments': len(segments)}

    a, b = evidence(baseline), evidence(negative)
    ok = (a['removed_region_mm'] > 10 and b['removed_region_mm'] < 0.01
          and min(a['retained_region_mm'], b['retained_region_mm']) > 10
          and a['layer_count'] == b['layer_count'])
    return {'pass': ok, 'body_box': body, 'cutter_box': cutter, 'removed_region': removed,
            'retained_region': retained, 'baseline': a, 'negative': b}
