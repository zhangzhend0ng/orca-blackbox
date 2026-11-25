"""Read-only checks for Feishu #251: an object imported from an STL and reloaded from disk.

Every function reads what the application put on disk (the project it saved and
the STL it was given) or what a dialog showed; nothing here drives the GUI.
World coordinates come from the saved 3MF through the per-instance reader that
tests/import_stl_oracle.py uses, and the vertex comparison is that module's
`_match` with its VERTEX_TOL_MM (0.001 mm): the STL stores float32 and the
project keeps the same corners as decimal text.
"""
import math
from pathlib import Path, PureWindowsPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from harness.model_move_pilot import stl_mesh
from import_stl_oracle import VERTEX_TOL_MM, _match, _need, _one, _shift
from part_attachment_oracle import _read

SETTINGS = 'Metadata/model_settings.config'
UNITS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
CLAUSE_RELOADED = '对象按磁盘最新文件重新加载，尺寸变为 30mm'
CLAUSE_MISSING = '文件被删则明确报错'
# "The source file ... does not exist" / "Missing file" / "reload_cube.stl was deleted".
# The gap stops at a sentence end; a path such as reload_cube.stl inside it is allowed.
_GONE = (r'not found|does not exist|do not exist|no longer exists|(?:cannot|can.t|could not) be found'
         r'|is missing|was (?:deleted|removed)|has been (?:deleted|removed)')
_THING = r'(?:file|source|\w+\.(?:stl|3mf|obj|ste?p|amf|svg))'
MISSING_FILE = re.compile(
    rf'\b{_THING}\b(?:(?!\.\s)[^!?\n]){{0,160}}\b(?:{_GONE})\b'
    rf'|\b(?:missing|deleted)\b(?:(?!\.\s)[^!?\n]){{0,40}}\b{_THING}\b',
    re.IGNORECASE)


def _source_file(project):
    """The `source_file` the saved project records for its only object."""
    with ZipFile(Path(project)) as archive:
        config = ET.fromstring(archive.read(SETTINGS))
    fields = config.findall("./object/part/metadata[@key='source_file']")
    _need(len(fields) == 1, f'expected one source_file entry, found {len(fields)}')
    return fields[0].get('value', '')


def _shape(project, source):
    """(the only instance, the STL's triangles): the instance holds exactly the STL's vertices.

    The application centres an imported STL on the plate, so every saved world
    vertex is the STL's own vertex plus one offset per axis; the instance axes
    must still be the STL's own, or a turned cube would pass as the same set."""
    _bed, item = _one(project)
    points, faces = stl_mesh(_read(Path(source)))
    for axis, unit in zip(item.basis, UNITS):
        _need(math.dist(axis, unit) <= VERTEX_TOL_MM, f'instance axis {axis} is not {unit}')
    offset = [item.box[i][0] - min(point[i] for point in points) for i in range(3)]
    _match(item.vertices, _shift(points, offset), 'reloaded mesh')
    _need(len(item.faces) == len(faces),
          f'project holds {len(item.faces)} triangles, the STL has {len(faces)}')
    return item, offset


def verify_cube(project, source, recorded=None, side=None):
    """The saved project holds exactly one object made of the vertices of the STL `source`.

    `recorded` is the path the project's `source_file` must name when that is
    not `source` itself (the original is gone and `source` is its retained
    copy); it defaults to `source`. `side` adds that each axis spans that many
    millimeters. Anything else raises ValueError."""
    item, offset = _shape(project, source)
    dimensions = [round(high - low, 6) for low, high in item.box]
    if side is not None:
        _need(all(abs(value - side) <= VERTEX_TOL_MM for value in dimensions),
              f'expected {side} mm on each axis, got {dimensions}')
    source_file = _source_file(project)
    expected = str(Path(recorded if recorded is not None else source))
    _need(source_file and PureWindowsPath(source_file) == PureWindowsPath(expected),
          f'project names source file {source_file}, expected {expected}')
    return {'dimensions_mm': dimensions, 'triangles': len(item.faces), 'source_file': source_file,
            # Always True here: a project that names another file raises above.
            'same_source': True, 'object_names': [item.name],
            'placement_offset_mm': [round(value, 6) for value in offset]}


def is_cube(reading, side):
    """Whether a verify_cube reading (or its refusal) shows `side` mm on every axis."""
    spans = reading.get('dimensions_mm')
    return bool(spans) and all(abs(value - side) <= VERTEX_TOL_MM for value in spans)


def clauses(before, reloaded, behavior, title, body):
    """The two Feishu clauses from the readings, as a saved analysis holds them."""
    return {CLAUSE_RELOADED: is_cube(before, 20) and is_cube(reloaded, 30),
            CLAUSE_MISSING: explicit_missing_error(behavior, title, body)}


def explicit_missing_error(behavior, title, body):
    """Only a message box whose text says that a file or source does not exist is an explicit error.

    `behavior` is what the case read from the dialog ('message dialog',
    'replacement file chooser', 'no dialog'). A file chooser is never one,
    whatever its title: it asks for another file without saying what is wrong.
    A short message box may keep the whole sentence in its title, so both are
    read."""
    if behavior != 'message dialog':
        return False
    return bool(MISSING_FILE.search(f'{title} {body}'))
