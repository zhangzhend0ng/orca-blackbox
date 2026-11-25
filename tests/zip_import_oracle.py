"""Offline disk evidence for Feishu #231 Import Zip Archive."""
import hashlib
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from harness.model_move_pilot import bounds, stl_mesh
from part_attachment_oracle import _facets, _read
from plate_layout_oracle import _pairs, _project as layout
from plate_reserve_oracle import read_project

EXPECTED = 'zip 内 3 个模型全部载入盘上/对象列表，无遗漏、无乱码文件名'
MEMBERS = (('cube_10mm.stl', 10), ('cube_20mm.stl', 20), ('cube_30mm.stl', 30))
NOTE = 'readme.txt'
# FileArchiveDialog.cpp (sm-v2.4.0) lists only these extensions; any other
# archive member is neither shown in the preview nor extracted.
LISTED = re.compile(r'\.(stl|obj|amf|3mf|step|stp)$', re.IGNORECASE)
SETTINGS = 'Metadata/model_settings.config'
TOL_MM = 0.0001


def digest(path):
    """Byte length and SHA-256 of a retained file (the harvest manifest carries the same pair)."""
    raw = _read(Path(path))
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _stem(name):
    return PurePosixPath(name).name.rsplit('.', 1)[0]


def model_members(archive):
    """[(member name, SHA-256)] of the archive entries the product can list as models."""
    with ZipFile(archive) as bundle:
        rows = []
        for entry in bundle.infolist():
            name = entry.filename
            if entry.is_dir() or name.startswith('__MACOSX') or not LISTED.search(name):
                continue
            rows.append((name, hashlib.sha256(bundle.read(entry)).hexdigest()))
    return sorted(rows)


def verify_member_digests(archive, sources):
    """The model entries of the zip must be exactly the retained source files, byte for byte."""
    members = model_members(archive)
    kept = sorted((name, digest(path)['sha256']) for name, path in sources.items())
    if not members or members != kept:
        raise ValueError(f'archive models {members} do not match the retained sources {kept}')
    return members


def _extent(points):
    return [high - low for low, high in bounds(points)]


def verify_zip_import(project, sources):
    """Every archive model on the one current plate, each under its file name, size and mesh."""
    wanted = sorted(_stem(name) for name in sources)
    meshes = {name: stl_mesh(_read(path)) for name, path in sources.items()}
    shapes = {name: _facets(*mesh) for name, mesh in meshes.items()}
    plates, instances = read_project(project)
    if len(plates) != 1:
        raise ValueError(f'expected the single current plate, found {list(plates)}')
    names = sorted(item.name for item in instances)
    if names != wanted:
        raise ValueError(f'loaded objects {names} are not exactly the archive models {wanted}')
    if any(item.plate != plates[0] for item in instances):
        raise ValueError(f'objects outside the current plate: {[(i.name, i.plate) for i in instances]}')
    readings = []
    for item in instances:
        source, = [name for name in sources if _stem(name) == item.name]
        size, expected = _extent(item.points), _extent(meshes[source][0])
        if any(abs(a - b) > TOL_MM for a, b in zip(size, expected)):
            raise ValueError(f'{item.name}: {size} mm instead of the source {expected} mm')
        if len(item.faces) != 12 or item.shape != shapes[source]:
            raise ValueError(f'{item.name}: saved triangles differ from {source}')
        readings.append({'name': item.name, 'dimensions_mm': size, 'bounds_mm': bounds(item.points),
                         'triangles': len(item.faces)})
    bed, placed = layout(project)
    overlaps = [pair for pair in _pairs(placed) if pair['overlap']]
    if overlaps:
        raise ValueError(f'imported objects overlap: {overlaps}')
    outside = [item.name for item in placed if not bed.contains(item)]
    if outside:
        raise ValueError(f'objects outside the printable area: {outside}')
    with ZipFile(project) as bundle:
        config = ET.fromstring(bundle.read(SETTINGS))
    origin = {}
    for row in config.findall('object'):
        field = row.find("./part/metadata[@key='source_file']")
        label = row.find("./metadata[@key='name']")
        if field is not None and label is not None:
            origin[label.get('value')] = field.get('value')
    return {'plate': plates[0], 'objects': readings, 'source_files': origin,
            'pairs': _pairs(placed), 'printable_area_mm': bed.polygon}


def _fold(text):
    # Drop punctuation (the underscore) but keep every letter, so that a
    # garbled or suffixed name never folds onto an expected one.
    return re.sub(r'[\W_]+', '', text.casefold())


def verify_object_list(words, names):
    """Each name must be readable in the object list: one OCR token, or joined
    neighbouring tokens of one text row (the underscore may split a name)."""
    rows = {}
    for text, x, y, _w, _h in words:
        folded = _fold(text)
        if folded:
            rows.setdefault(round(y / 10), []).append((x, folded))
    tokens = set()
    for row in rows.values():
        parts = [folded for _x, folded in sorted(row)]
        for start in range(len(parts)):
            tokens.update(''.join(parts[start:start + span]) for span in (1, 2, 3, 4))
    missing = [name for name in names if _fold(name) not in tokens]
    if missing:
        raise ValueError(f'object list does not show {missing}; read {[word[0] for word in words]}')
    return {'names': list(names), 'read_words': [word[0] for word in words]}


def temp_collisions(temp_dir, sources):
    """Names of our members that already exist in the product's extraction directory."""
    temp = Path(temp_dir)
    return sorted(name for name in sources if (temp / name).exists())


def remove_stale(temp_dir, sources):
    """Delete a leftover only when it is byte-identical to this run's source file.

    The product extracts into the system temp dir and renames an entry whose
    name already exists there (Plater.cpp load_files, sm-v2.4.0:
    cube_10mm.stl -> cube_10mm(1).stl), which renames the imported object.
    """
    removed = []
    for name, path in sources.items():
        leftover = Path(temp_dir) / name
        try:
            same = leftover.is_file() and digest(leftover) == digest(path)
        except (OSError, ValueError):
            same = False
        if same:
            leftover.unlink()
            removed.append(name)
    return removed
