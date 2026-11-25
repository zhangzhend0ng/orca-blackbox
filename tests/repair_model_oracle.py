"""Offline disk evidence for Feishu #246 Fix model."""
from collections import Counter
from itertools import combinations
from pathlib import Path

from harness.model_move_pilot import bounds, stl_mesh
from part_attachment_oracle import _facets, _read
from plate_reserve_oracle import read_project

EXPECTED = '模型被修复（孔洞补齐）、可正常切片，或给出无法修复的明确提示'
FIX_ROW = 'Fix model'
# ObjectList::fix_through_netfabb reports failures in an in-app notification
# (GUI_ObjectList.cpp:5655, sm-v2.4.0): "Failed to repair following model object".
EXPLICIT = ('failed to repair', 'could not be repaired', 'cannot be repaired', 'unable to repair')
# The twelve triangles of the cube that m7x_251 write_cube writes.
FACES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
DROPPED = 4  # one side face, leaving a triangular hole with three open edges
TOL_MM = 0.0001


def write_holed_cube(path, size=20):
    """The cube of m7x_251 write_cube with triangle DROPPED left out: a binary STL of
    eleven triangles around a triangular hole (three open edges)."""
    import struct

    corners = ((0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0),
               (0, 0, size), (size, 0, size), (size, size, size), (0, size, size))
    kept = [face for index, face in enumerate(FACES) if index != DROPPED]
    with Path(path).open('wb') as output:
        output.write(struct.pack('<80sI', b'Orca black-box #246 holed cube', len(kept)))
        for face in kept:
            output.write(struct.pack('<12fH', 0, 0, 0, *(axis for i in face for axis in corners[i]), 0))
    return path


def _welded(points, faces):
    """Triangle indices over coincident vertices merged (a binary STL repeats every corner)."""
    seen, merged = {}, []

    def key(point):
        return tuple(round(value / TOL_MM) for value in point)

    for face in faces:
        for index in face:
            if key(points[index]) not in seen:
                seen[key(points[index])] = len(seen)
        merged.append(tuple(seen[key(points[index])] for index in face))
    return merged


def edge_report(points, faces):
    """Closed means every edge is shared by exactly two triangles."""
    used = Counter(tuple(sorted(edge)) for face in _welded(points, faces)
                   for edge in combinations(face, 2))
    return {'triangles': len(faces), 'vertices': len({index for face in faces for index in face}),
            'open_edges': sum(1 for uses in used.values() if uses == 1),
            'nonmanifold_edges': sum(1 for uses in used.values() if uses > 2),
            'closed': bool(used) and all(uses == 2 for uses in used.values())}


def cube_triangles(points):
    """The twelve triangles of the axis-aligned box around `points`."""
    (x0, x1), (y0, y1), (z0, z1) = bounds(points)
    corners = ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
               (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
    return _facets(corners, FACES)


def _sole(path):
    plates, instances = read_project(path)
    if len(plates) != 1 or len(instances) != 1 or instances[0].plate != plates[0]:
        raise ValueError(f'{Path(path).name}: expected one object on the one current plate')
    return instances[0]


def initial_state(project, holed):
    """The imported object must be the holed cube: open, and exactly one cube triangle short."""
    item = _sole(project)
    points, faces = stl_mesh(_read(holed))
    report = edge_report(item.points, item.faces)
    cube = set(cube_triangles(points))
    saved = set(item.shape)
    if item.shape != _facets(points, faces) or report['closed'] or not saved < cube or len(cube - saved) != 1:
        raise ValueError(f'saved object is not the imported holed cube: {report}')
    return {**report, 'missing_triangles': len(cube - saved)}


def repair_reading(project, holed):
    """Closed, and still the original cube: the same twelve triangles and the same box."""
    item = _sole(project)
    source = stl_mesh(_read(holed))[0]
    report = edge_report(item.points, item.faces)
    report['is_cube'] = item.shape == cube_triangles(source)
    report['dimensions_mm'] = [high - low for low, high in bounds(item.points)]
    report['same_box'] = all(abs(a - b) <= TOL_MM for a, b in
                             zip(report['dimensions_mm'], (high - low for low, high in bounds(source))))
    return report


def repaired(reading):
    return bool(reading) and reading['closed'] and reading['is_cube'] and reading['same_box']


def row_label(text):
    return text.partition('\t')[0].rstrip('. …').strip()


def menu_rows(rows):
    """Every row of a live HMENU with its enabled state, separator and submenu flags."""
    return [{'index': index, 'label': text, 'enabled': not flags & 3, 'separator': bool(flags & 0x800),
             'submenu': bool(flags & 0x10)} for index, text, flags in rows]


def fix_row(rows):
    """The one `Fix model` row of a context menu as {'index', 'label', 'enabled'}, or None."""
    found = [row for row in menu_rows(rows) if row_label(row['label']).casefold() == FIX_ROW.casefold()]
    if len(found) > 1:
        raise ValueError(f'{len(found)} rows are named {FIX_ROW!r}')
    return found[0] if found else None


def judge(row, reading, sliced, prompt_texts) -> str:
    """Value of the Feishu expectation: repaired and slices, or an explicit statement that it cannot be."""
    done = repaired(reading)
    explicit = any(word in ' '.join(prompt_texts).casefold() for word in EXPLICIT)
    problems = []
    if row is None:
        problems.append(f'no "{FIX_ROW}" row in the context menu')
    elif not row['enabled']:
        problems.append(f'"{FIX_ROW}" row is disabled')
    if (done and sliced) or (explicit and not done):
        return 'PASS'
    if not done:
        problems.append('hole not closed' if reading and not reading['closed'] else 'not the original cube')
    if not sliced:
        problems.append('did not finish slicing')
    return 'FAIL (' + '; '.join(problems) + ')'


def missing_row_verdict(row_count, initial, os_caption=None):
    """The readable result when the object menu has no `Fix model` row on this system."""
    where = f' on {os_caption}' if os_caption else ' on this system'
    return (f'FAIL (the object menu has no "{FIX_ROW}" row{where}: {row_count} rows read; '
            f'no repair was attempted and the model was not sliced; '
            f'the hole stays open with {initial["open_edges"]} open edges in before.3mf)')


def verify_digests(files):
    """Every retained file must still have the byte length and SHA-256 recorded for it."""
    from zip_import_oracle import digest

    for path, expected in files.items():
        actual = digest(path)
        if actual != expected:
            raise ValueError(f'{Path(path).name}: {actual} is not the recorded {expected}')
    return sorted(Path(path).name for path in files)
