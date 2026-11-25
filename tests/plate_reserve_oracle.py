"""Offline project geometry for the Delete Plate, Split and STL witnesses."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
from xml.dom import minidom
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from delete_object_oracle import create_fixture as create_named_pair
from harness.model_move_pilot import bounds, stl_mesh, transform_point
from harness.project_3mf import _CORE, _PROD
from part_attachment_oracle import _facets, _mesh, _metadata, _read, _transform


MAIN = '3D/3dmodel.model'
SETTINGS = 'Metadata/model_settings.config'


@dataclass(frozen=True)
class Instance:
    name: str
    plate: str | None
    points: tuple
    faces: tuple
    extruder: str | None

    @property
    def world_faces(self):
        return tuple(sorted(tuple(sorted(tuple(round(x, 5) for x in self.points[i])
                                         for i in f)) for f in self.faces))

    @property
    def shape(self):
        return _facets(self.points, self.faces)


def read_project(path):
    """Read one normal mesh per instance, including an unassigned build item."""
    with ZipFile(path) as archive:
        main = ET.fromstring(archive.read(MAIN))
        config = ET.fromstring(archive.read(SETTINGS))
        plate_nodes = config.findall('plate')
        plate_ids = [_metadata(p, 'plater_id') for p in plate_nodes]
        if not plate_ids or len(set(plate_ids)) != len(plate_ids) or not all(plate_ids):
            raise ValueError('expected a nonempty list of uniquely identified plates')
        plates = tuple(_metadata(p, 'plater_name') or pid
                       for p, pid in zip(plate_nodes, plate_ids))
        if len(set(plates)) != len(plates):
            raise ValueError('plate names collide')
        assigned = {}
        for label, plate in zip(plates, plate_nodes):
            for row in plate.findall('model_instance'):
                obj = _metadata(row, 'object_id')
                if not obj or obj in assigned or _metadata(row, 'instance_id') != '0':
                    raise ValueError('expected one instance per object')
                assigned[obj] = label

        items = main.findall(_CORE + 'build/' + _CORE + 'item')
        settings = {obj.get('id'): obj for obj in config.findall('object')}
        ids = {i.get('objectid') for i in items}
        if len(items) != len(ids) or ids != set(settings) or not set(assigned) <= ids:
            raise ValueError('build, object list and plate membership disagree')
        instances = []
        for item in items:
            object_id = item.get('objectid')
            row = settings[object_id]
            parent = main.find(f".//{_CORE}object[@id='{object_id}']")
            part, = row.findall('part')
            component, = parent.findall(_CORE + 'components/' + _CORE + 'component')
            if part.get('subtype') != 'normal_part' or component.get('objectid') != part.get('id'):
                raise ValueError('invalid object component membership')
            model_path = component.get(_PROD + 'path', MAIN).lstrip('/')
            model = main if model_path == MAIN else ET.fromstring(archive.read(model_path))
            mesh = model.find(f".//{_CORE}object[@id='{part.get('id')}']")
            points, faces = _mesh(mesh)
            local, world = _transform(component), _transform(item)
            vertices = tuple(transform_point(transform_point(p, local), world) for p in points)
            instances.append(Instance(_metadata(row, 'name'), assigned.get(object_id),
                                      vertices, tuple(faces), _metadata(part, 'extruder') or _metadata(row, 'extruder')))
    return plates, instances


def create_delete_plate_fixture(template, output):
    pair = output.with_name('Alpha-Bravo.3mf')
    create_named_pair(template, pair)
    with ZipFile(pair) as src, ZipFile(output, 'w') as dst:
        settings = json.loads(src.read('Metadata/project_settings.config'))
        printable_x = [float(point.split('x')[0]) for point in settings['printable_area']]
        offset = 1.2 * (max(printable_x) - min(printable_x))
        for entry in src.infolist():
            raw = src.read(entry)
            if entry.filename == SETTINGS:
                root = ET.fromstring(raw)
                first, = root.findall('plate')
                second = deepcopy(first)
                first.remove(first.findall('model_instance')[1])
                second.remove(second.findall('model_instance')[0])
                for plate, label in [(first, 'Keep'), (second, 'Remove')]:
                    plate.find("metadata[@key='plater_name']").set('value', label)
                second.find("metadata[@key='plater_id']").set('value', '2')
                for row in list(second.findall('metadata')):
                    if row.get('key').endswith('_file'):
                        second.remove(row)
                root.insert(list(root).index(first) + 1, second)
                raw = ET.tostring(root, encoding='utf-8')
            elif entry.filename == MAIN:
                dom = minidom.parseString(raw)
                _, second = dom.getElementsByTagName('item')
                matrix = second.getAttribute('transform').split()
                matrix[9] = str(offset + 135)
                second.setAttribute('transform', ' '.join(matrix))
                raw = dom.toxml(encoding='utf-8')
            dst.writestr(entry, raw)


def verify_delete_plate(before, after):
    before_plates, start_items = read_project(before)
    after_plates, end_items = read_project(after)
    first = {i.name: i for i in start_items}
    final = {i.name: i for i in end_items}
    if before_plates != ('Keep', 'Remove') or {k: i.plate for k, i in first.items()} != {'Alpha': 'Keep', 'Bravo': 'Remove'}:
        raise ValueError('expected Keep/Alpha and Remove/Bravo on the two initial plates')
    if after_plates != ('Keep',):
        raise ValueError(f'wrong plate survived: {after_plates!r}')
    if len(start_items) != len(end_items) or set(final) != set(first):
        raise ValueError('one or more original instances were lost or duplicated')
    if first['Alpha'].world_faces != final['Alpha'].world_faces or final['Alpha'].plate != 'Keep':
        raise ValueError('the surviving plate lost or moved Alpha')
    if first['Bravo'].shape != final['Bravo'].shape:
        raise ValueError('the deleted plate did not retain the original Bravo mesh')
    return {'before': list(before_plates), 'after': list(after_plates),
            'objects_before': {k: i.plate for k, i in first.items()},
            'objects_after': {k: i.plate or 'unassigned' for k, i in final.items()},
            'bravo_bounds_mm': bounds(final['Bravo'].points)}


def create_split_fixture(template, output):
    """Put two separated, differently sized closed shells into one editable mesh."""
    with ZipFile(template) as src, ZipFile(output, 'w') as dst:
        for entry in src.infolist():
            raw = src.read(entry)
            if entry.filename == SETTINGS:
                root = ET.fromstring(raw)
                obj, = root.findall('object')
                for node in obj.findall(".//metadata[@key='name']"):
                    node.set('value', 'TwinShell')
                raw = ET.tostring(root, encoding='utf-8')
            elif entry.filename.startswith('3D/Objects/') and entry.filename.endswith('.model'):
                dom = minidom.parseString(raw)
                vertices, = dom.getElementsByTagName('vertices')
                triangles, = dom.getElementsByTagName('triangles')
                base_vertices = list(vertices.getElementsByTagName('vertex'))
                base_faces = list(triangles.getElementsByTagName('triangle'))
                z_min = min(float(v.getAttribute('z')) for v in base_vertices)
                for vertex in base_vertices:
                    clone = vertex.cloneNode(deep=False)
                    clone.setAttribute('x', str(float(vertex.getAttribute('x')) * 0.8 + 65))
                    clone.setAttribute('y', str(float(vertex.getAttribute('y')) * 0.9))
                    z = float(vertex.getAttribute('z'))
                    clone.setAttribute('z', str(z_min + (z - z_min) * 0.7))
                    vertices.appendChild(clone)
                for face in base_faces:
                    clone = face.cloneNode(deep=False)
                    for key in ('v1', 'v2', 'v3'):
                        clone.setAttribute(key, str(int(face.getAttribute(key)) + len(base_vertices)))
                    triangles.appendChild(clone)
                raw = dom.toxml(encoding='utf-8')
            dst.writestr(entry, raw)


def _connected_shells(instance):
    faces = instance.world_faces
    incident = {}
    edges = Counter()
    for i, face in enumerate(faces):
        if len(set(face)) != 3:
            raise ValueError('degenerate facet in shell fixture')
        for vertex in face:
            incident.setdefault(vertex, []).append(i)
        edges.update((face[0:2], (face[0], face[2]), face[1:3]))
    if set(edges.values()) != {2}:
        raise ValueError('the mesh does not consist of closed two-manifold shells')
    remaining = set(range(len(faces)))
    shells = []
    while remaining:
        start = remaining.pop()
        todo, shell = [start], [faces[start]]
        while todo:
            for vertex in faces[todo.pop()]:
                for nxt in incident[vertex]:
                    if nxt in remaining:
                        remaining.remove(nxt)
                        todo.append(nxt)
                        shell.append(faces[nxt])
        shells.append(tuple(sorted(shell)))
    return shells


def _split_instances(project):
    plates, instances = read_project(project)
    if (len(plates) != 1 or len(instances) != 2
            or any(i.plate != plates[0] or len(_connected_shells(i)) != 1 for i in instances)):
        raise ValueError('expected two independently stored closed meshes on the plate')
    return sorted(instances, key=lambda item: bounds(item.points)[0][0])


def verify_split(before, split):
    plates, instances = read_project(before)
    if len(plates) != 1 or len(instances) != 1 or instances[0].plate != plates[0]:
        raise ValueError('expected one original model on one plate')
    shells = _connected_shells(instances[0])
    if len(shells) != 2:
        raise ValueError(f'expected two disconnected initial shells, found {len(shells)}')
    objects = _split_instances(split)
    if Counter(shells) != Counter(obj.world_faces for obj in objects):
        raise ValueError('split did not preserve each original closed shell at its plate position')
    return {'initial_shell_triangle_counts': sorted(map(len, shells)),
            'split_object_names': [obj.name for obj in objects],
            'object_bounds_mm': [bounds(obj.points) for obj in objects]}


def verify_split_selection(split, left_color, both_colors):
    first, intermediate, final = map(_split_instances, (split, left_color, both_colors))
    if any(a.world_faces != b.world_faces or a.world_faces != c.world_faces
           for a, b, c in zip(first, intermediate, final)):
        raise ValueError('selection/coloring unexpectedly changed split geometry')
    first_slots, left_slots, final_slots = ([obj.extruder for obj in items] for items in (first, intermediate, final))
    if (left_slots != ['2', first_slots[1]] or left_slots[0] == first_slots[0]
            or final_slots != ['2', '3'] or final_slots[1] == left_slots[1]):
        raise ValueError(f'coloring did not independently update the two selected objects: {first_slots}, {left_slots}, {final_slots}')
    with ZipFile(both_colors) as saved:
        colors = json.loads(saved.read('Metadata/project_settings.config'))['filament_colour']
    if len(set(colors[1:3])) != 2:
        raise ValueError('saved filament slots do not represent visibly distinct colors')
    return {'slots_before': first_slots, 'slots_after_left': left_slots, 'slots_after_both': final_slots,
            'colors_after_both': colors[1:3]}


def verify_stl(project, exported):
    plates, models = read_project(project)
    if len(plates) != 1 or len(models) != 1 or models[0].plate != plates[0]:
        raise ValueError('expected exactly one original object on the selected plate')
    raw = _read(exported)
    points, faces = stl_mesh(raw)
    if models[0].shape != _facets(points, faces):
        raise ValueError('STL does not contain all original triangles at the original orientation')
    return {'file_bytes': len(raw), 'triangle_count': len(faces), 'bounds_mm': bounds(points)}


def verify_f3d_image(path):
    """Reject empty, opaque-background and flat-placeholder render outputs."""
    from PIL import Image

    with Image.open(path) as image:
        if image.format != 'PNG' or 'A' not in image.getbands() or not all(200 <= side <= 1800 for side in image.size):
            raise ValueError('F3D did not retain a bounded transparent PNG')
        alpha = image.getchannel('A')
        mask = alpha.point(lambda value: 255 if value >= 180 else 0)
        box = mask.getbbox()
        width, height = image.size
        count = mask.histogram()[255]
        if (box is None or not (0 < box[0] < box[2] < width and 0 < box[1] < box[3] < height)
                or not width * height * 0.015 <= count <= width * height * 0.8):
            raise ValueError('F3D did not show a bounded foreground mesh')
        colors = image.crop(box).getcolors(maxcolors=width * height)
        distinct = sum(1 for num, rgba in colors if num > 10 and rgba[-1] >= 180)
        if distinct < 3:
            raise ValueError('F3D foreground does not show multiple shaded surfaces')
    return {'width_px': width, 'height_px': height, 'visible_mesh_pixels': count,
            'mesh_bbox_px': box, 'shaded_colors': distinct}
