"""Read-only checks for Feishu #227: a binary STL imported through File > Import.

Every function reads what the application put on disk (the project it saved and
the STL it was given) or what the dialog showed; nothing here drives the GUI.
World coordinates come from the saved 3MF through plate_layout_oracle, the
same per-instance reader the plate cases use.
"""
import json
import math
from pathlib import Path, PureWindowsPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from harness.model_move_pilot import stl_mesh
from import_model_oracle import selected_printer
from part_attachment_oracle import _metadata, _read
from plate_layout_oracle import _project

STL_FILTER = re.compile(r'\*\.stl\b', re.IGNORECASE)
VERTEX_TOL_MM = 0.001  # the STL stores float32; a 20 mm vertex is exact to about 1e-6 mm
SOURCE_NAME = 'cube_20mm.stl'
SIDE_MM = 20.0


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def stl_filter_label(labels):
    """The first text that offers `*.stl`, or None when none of `labels` does."""
    for text in labels:
        if text and STL_FILTER.search(text):
            return text
    return None


def _one(project):
    """(bed, the only instance) of a saved project that holds exactly one object."""
    bed, instances = _project(Path(project))
    _need(len(instances) == 1,
          f'expected exactly one object on the plate, found {len(instances)}: {[i.name for i in instances]}')
    return bed, instances[0]


def _unique(points):
    """The distinct vertices of a mesh (an STL repeats each corner for every facet)."""
    out = []
    for point in points:
        if not any(math.dist(other, point) <= VERTEX_TOL_MM for other in out):
            out.append(tuple(point))
    return out


def _match(actual, expected, what):
    """Every expected vertex has its own actual vertex within the tolerance, and there is no extra one."""
    actual, expected = _unique(actual), _unique(expected)
    _need(len(actual) == len(expected),
          f'{what}: {len(actual)} distinct vertices saved, {len(expected)} expected')
    remaining = list(actual)
    for point in expected:
        hit = next((i for i, other in enumerate(remaining) if math.dist(other, point) <= VERTEX_TOL_MM), None)
        _need(hit is not None, f'{what}: no saved vertex within {VERTEX_TOL_MM} mm of '
                               f'{tuple(round(c, 4) for c in point)}')
        remaining.pop(hit)


def _shift(points, delta):
    return [tuple(p[i] + delta[i] for i in range(3)) for p in points]


def _centroid(points):
    count = len(points)
    return tuple(sum(p[i] for p in points) / count for i in range(3))


def verify_imported(project, source):
    """The saved project holds exactly the imported STL as one 20 mm object on the current plate."""
    project, source = Path(project), Path(source)
    bed, item = _one(project)
    points, faces = stl_mesh(_read(source))
    box = item.box
    dimensions = [round(high - low, 6) for low, high in box]
    _need(all(abs(value - SIDE_MM) <= VERTEX_TOL_MM for value in dimensions),
          f'expected {SIDE_MM} mm on each axis, got {dimensions}')
    # The imported object keeps the STL's own axes: its instance basis is the identity.
    for axis, unit in zip(item.basis, ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        _need(math.dist(axis, unit) <= VERTEX_TOL_MM, f'instance axis {axis} is not {unit}')
    source_box = [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(3)]
    offset = [box[i][0] - source_box[i][0] for i in range(3)]
    _match(item.vertices, _shift(points, offset), 'imported mesh')
    with ZipFile(project) as archive:
        config = ET.fromstring(archive.read('Metadata/model_settings.config'))
        settings = json.loads(archive.read('Metadata/project_settings.config'))
    field = config.find("./object/part/metadata[@key='source_file']")
    recorded = PureWindowsPath(field.get('value', '')).name if field is not None else None
    _need(recorded == source.name, f'unexpected imported source: {recorded}')
    _need(recorded == SOURCE_NAME, f'the case imports {SOURCE_NAME}, the project names {recorded}')
    plates = config.findall('plate')
    _need(len(plates) == 1, f'expected a single current plate, found {len(plates)}')
    # The application names an imported single-mesh file after its file name, with or without the extension.
    names = [_metadata(row, 'name') for row in config.findall('object')]
    _need(len(names) == 1 and names[0] in (source.stem, source.name),
          f'object list names {names}, expected {[source.stem]} or {[source.name]}')
    _need(bed.contains(item), 'the imported object is not inside the printable area')
    _need(abs(box[2][0]) <= VERTEX_TOL_MM, 'the imported object does not rest on the plate')
    return {'object_names': names, 'source_file': str(recorded), 'dimensions_mm': dimensions,
            'world_box_mm': [list(pair) for pair in box], 'placement_offset_mm': [round(v, 6) for v in offset],
            'triangles': len(faces), 'printer': selected_printer(project), 'plates': len(plates)}


def verify_moved(before, after, axis='x', distance=10.0):
    """The only object moved by `distance` mm along `axis`; its mesh, orientation and size are unchanged."""
    first_bed, first = _one(before)
    last_bed, last = _one(after)
    _need(axis in 'xyz', f'axis must be x, y or z, got {axis!r}')
    expected = [0.0, 0.0, 0.0]
    _need(math.isfinite(distance) and abs(distance) > VERTEX_TOL_MM, 'expected a nonzero finite move')
    expected['xyz'.index(axis)] = float(distance)
    _need(first.name == last.name, f'object renamed by the move: {first.name!r} -> {last.name!r}')
    delta = [round(last.box[i][0] - first.box[i][0], 6) for i in range(3)]
    _need(all(abs(a - b) <= VERTEX_TOL_MM for a, b in zip(delta, expected)),
          f'object did not move {expected} mm; measured {delta} mm')
    _match(last.vertices, _shift(first.vertices, expected), 'moved mesh')
    _need(first_bed == last_bed and last_bed.contains(last), 'the moved object is not inside the printable area')
    return {'delta_mm': delta, 'before_box_mm': [list(pair) for pair in first.box],
            'after_box_mm': [list(pair) for pair in last.box]}


def _rotated(points, degrees):
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return [(cos * x - sin * y, sin * x + cos * y, z) for x, y, z in points]


def verify_rotated(before, after, degrees=45.0):
    """The only object turned by `degrees` about the vertical axis (either way), keeping its size and centroid."""
    first_bed, first = _one(before)
    last_bed, last = _one(after)
    _need(first.name == last.name, f'object renamed by the rotation: {first.name!r} -> {last.name!r}')
    failures = []
    for sign in (1, -1):
        turned = _rotated(first.vertices, sign * degrees)
        pivot = [a - b for a, b in zip(_centroid(last.vertices), _centroid(turned))]
        try:
            _match(last.vertices, _shift(turned, pivot), 'rotated mesh')
        except ValueError as exc:
            failures.append(f'{sign * degrees:+.0f}°: {exc}')
            continue
        _need(first_bed == last_bed and last_bed.contains(last),
              'the rotated object is not inside the printable area')
        _need(abs(last.box[2][0]) <= VERTEX_TOL_MM and
              abs((last.box[2][1] - last.box[2][0]) - (first.box[2][1] - first.box[2][0])) <= VERTEX_TOL_MM,
              'the rotated object does not rest on the plate at its former height')
        return {'degrees_about_z': sign * degrees, 'pivot_shift_mm': [round(v, 6) for v in pivot],
                'before_box_mm': [list(pair) for pair in first.box],
                'after_box_mm': [list(pair) for pair in last.box]}
    raise ValueError('object was not turned by {:.0f}° about the vertical axis: '.format(degrees)
                     + '; '.join(failures))


def _compact(text):
    return re.sub(r'[\s_.\-|:;,\[\]()]+', '', str(text)).casefold()


def _distance(first, second):
    """Levenshtein distance; OCR may misread one character of an underscored name."""
    row = list(range(len(second) + 1))
    for i, a in enumerate(first, 1):
        next_row = [i]
        for j, b in enumerate(second, 1):
            next_row.append(min(row[j] + 1, next_row[j - 1] + 1, row[j - 1] + (a != b)))
        row = next_row
    return row[-1]


def _candidates(words):
    """Every OCR word, plus every pair of neighbours on one sidebar line (a name may be read as two words)."""
    lines = {}
    for word in words:
        text, x, y, _w, h = (list(word) + [0] * 5)[:5]
        middle = y + h / 2
        key = next((k for k in lines if abs(k - middle) <= max(3, h / 2)), None)
        lines.setdefault(middle if key is None else key, []).append((x, str(text)))
    out = [str(word[0]) for word in words]
    for row in lines.values():
        texts = [text for _x, text in sorted(row)]
        out += [''.join(pair) for pair in zip(texts, texts[1:])]
    return out


def listed_object_names(words, expected):
    """The object-list OCR words that name the expected objects.

    Underscores, dots and spacing are ignored and one misread character is
    tolerated, so `cube_20mm`, `cube20mm.stl`, `cube 20mm` and `cube_20mn` all
    name `cube_20mm`. Every expected name must be found exactly once."""
    found = []
    for name in expected:
        wanted = _compact(name)
        hits = [text for text in _candidates(words)
                if _distance(_compact(text).removesuffix('stl'), wanted) <= 1]
        _need(len(hits) == 1, f'object list OCR names {name!r} {len(hits)} times: {hits!r} '
                              f'among {[word[0] for word in words]!r}')
        found.append(hits[0])
    return found
