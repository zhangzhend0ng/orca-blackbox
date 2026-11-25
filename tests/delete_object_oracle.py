"""Two-object deletion and Ctrl+Z witnesses for #248."""
from collections import Counter
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from harness.model_move_pilot import transform_point
from harness.project_3mf import _CORE, _PROD
from part_attachment_oracle import _mesh, _metadata, _transform


def create_fixture(template, output):
    """Use the existing spaced cubes; give the right-hand witness a distinct mesh."""
    with ZipFile(template) as src, ZipFile(output, 'w') as dst:
        for entry in src.infolist():
            data = src.read(entry)
            if entry.filename == 'Metadata/model_settings.config':
                root = ET.fromstring(data)
                for obj, label in zip(root.findall('object'), ('Alpha', 'Bravo'), strict=True):
                    for name in obj.findall(".//metadata[@key='name']"):
                        name.set('value', label)
                data = ET.tostring(root, encoding='utf-8')
            elif entry.filename.startswith('3D/Objects/') and entry.filename.endswith('_2.model'):
                document = minidom.parseString(data)
                for vertex in document.getElementsByTagName('vertex'):
                    for axis, factor in zip('xyz', (0.8, 0.7, 0.6)):
                        vertex.setAttribute(axis, str(float(vertex.getAttribute(axis)) * factor))
                data = document.toxml(encoding='utf-8')
            dst.writestr(entry, data)


def objects(path):
    """Return named physical triangles, independent of archive ordering and renumbering."""
    with ZipFile(path) as archive:
        main = ET.fromstring(archive.read('3D/3dmodel.model'))
        config = ET.fromstring(archive.read('Metadata/model_settings.config'))
        items = main.findall(_CORE + 'build/' + _CORE + 'item')
        ids = [item.get('objectid') for item in items]
        plate_ids = [_metadata(i, 'object_id') for i in config.findall('plate/model_instance')]
        models = {node.get('id'): node for node in config.findall('object')}
        if len(config.findall('plate')) != 1 or Counter(plate_ids) != Counter(ids) or set(ids) != set(models):
            raise ValueError('plate instances or object list differ from the build')
        snapshots = {}
        for item in items:
            obj_id = item.get('objectid')
            name = _metadata(models[obj_id], 'name')
            obj = main.find(f".//{_CORE}object[@id='{obj_id}']")
            part, = models[obj_id].findall('part')
            component, = obj.findall(_CORE + 'components/' + _CORE + 'component')
            if (name in snapshots or not name or item.get('printable','1') != '1'
                    or component.get('objectid') != part.get('id') or part.get('subtype') != 'normal_part'):
                raise ValueError('invalid object/part membership')
            model = ET.fromstring(archive.read(component.get(_PROD + 'path').lstrip('/')))
            mesh = model.find(f".//{_CORE}object[@id='{part.get('id')}']")
            points, triangles = _mesh(mesh)
            local, world = _transform(component), _transform(item)
            vertices = [tuple(round(v, 5) for v in transform_point(transform_point(p, local), world)) for p in points]
            snapshots[name] = tuple(sorted(tuple(sorted(vertices[i] for i in face)) for face in triangles))
    return snapshots


def verify_sequence(before, deleted, restored):
    first, remaining, final = map(objects, (before, deleted, restored))
    if set(first) != {'Alpha', 'Bravo'} or remaining != {'Bravo': first['Bravo']} or final != first:
        raise ValueError(f'wrong deletion, restoration or world-space geometry: {list(first)}, {list(remaining)}, {list(final)}')
    return {name: [[min(v[i] for f in faces for v in f), max(v[i] for f in faces for v in f)] for i in range(3)]
            for name, faces in first.items()}
