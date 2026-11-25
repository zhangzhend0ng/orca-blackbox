"""Deterministic one-plate projects for the Feishu plate layout cases."""
from copy import deepcopy
from xml.dom import minidom
from zipfile import ZipFile


FACES = (
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
)


def _box(width, depth, height, *, tipped=False):
    x, y = width / 2, depth / 2
    bottom = [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0)]
    if tipped:
        # Asymmetric taper in Y; the flat side at +X is narrower than the base.
        top = [(-x, -y*.55, height), (x, -y*.55, height),
               (x, y*.35, height), (-x, y*.35, height)]
        return [(z-height/2, y, x*-1+width/2) for x, y, z in bottom + top]
    return bottom + [(x, y, height) for x, y, _ in bottom]


def create_fixture(template, output, case):
    specifications = {
        240: [('Alpha', (30, 24, 11), (129, 130)),
              ('Bravo', (27, 33, 15), (135, 134)),
              ('Charlie', (34, 29, 20), (142, 133))],
        241: [('Alpha', (55, 33, 11), (92, 132)),
              ('Bravo', (62, 39, 15), (176, 132))],
        245: [('Alpha', (42, 38, 24), (135, 135))],
    }
    model_name = '3D/3dmodel.model'
    config_name = 'Metadata/model_settings.config'
    rels_name = '3D/_rels/3dmodel.model.rels'
    with ZipFile(template) as src, ZipFile(output, 'w') as dst:
        model = minidom.parseString(src.read(model_name))
        config = minidom.parseString(src.read(config_name))
        rels = minidom.parseString(src.read(rels_name))
        model_resources = model.getElementsByTagName('resources')[0]
        build = model.getElementsByTagName('build')[0]
        plate = config.getElementsByTagName('plate')[0]
        assemble = config.getElementsByTagName('assemble')[0]
        resource_seed = model.getElementsByTagName('object')[0]
        component_seed = resource_seed.getElementsByTagName('component')[0]
        mesh_seed = src.read(component_seed.getAttribute('p:path').lstrip('/'))
        object_seed = config.getElementsByTagName('object')[0]
        # These are the template's per-instance tables. Preserve all plate
        # metadata, including the selected preset and thumbnail references.
        for element in list(model.getElementsByTagName('object')) + list(build.getElementsByTagName('item')) + list(
            config.getElementsByTagName('object')
        ) + list(plate.getElementsByTagName('model_instance')) + list(assemble.getElementsByTagName('assemble_item')) + list(
            rels.getElementsByTagName('Relationship')
        ):
            element.parentNode.removeChild(element)

        for index, (name, dimensions, (x, y)) in enumerate(specifications[case], 1):
            part_id = str(index)
            object_id = str(index + 10)
            path = f'3D/Objects/{name}.model'
            transform = f'1 0 0 0 1 0 0 0 1 {x} {y} 0'
            resource = deepcopy(resource_seed)
            resource.setAttribute('id', object_id)
            resource.setAttribute('p:UUID', f'000000{index:02x}-61cb-4c03-9d28-80fed5dfa1dc')
            component = resource.getElementsByTagName('component')[0]
            component.setAttribute('objectid', part_id)
            component.setAttribute('p:path', '/' + path)
            component.setAttribute('p:UUID', f'{index:04x}0000-b206-40ff-9872-83e8017abed1')
            model_resources.appendChild(resource)
            item = model.createElement('item')
            for key, value in {'objectid': object_id, 'transform': transform, 'printable': '1',
                               'p:UUID': f'{index:08x}-b1ec-4553-aec9-835e5b724bb4'}.items():
                item.setAttribute(key, value)
            build.appendChild(item)

            obj = deepcopy(object_seed)
            obj.setAttribute('id', object_id)
            obj.getElementsByTagName('part')[0].setAttribute('id', part_id)
            for node in obj.getElementsByTagName('metadata'):
                if node.getAttribute('key') == 'name':
                    node.setAttribute('value', name)
            config.documentElement.insertBefore(obj, plate)
            instance = config.createElement('model_instance')
            for key, value in {'object_id': object_id, 'instance_id': '0', 'identify_id': str(90+index)}.items():
                node = config.createElement('metadata')
                node.setAttribute('key', key)
                node.setAttribute('value', value)
                instance.appendChild(node)
            plate.appendChild(instance)
            assembled = config.createElement('assemble_item')
            for key, value in {'object_id': object_id, 'instance_id': '0',
                               'transform': transform, 'offset': '0 0 0'}.items():
                assembled.setAttribute(key, value)
            assemble.appendChild(assembled)

            rel = rels.createElement('Relationship')
            rel.setAttribute('Target', '/' + path)
            rel.setAttribute('Id', f'rel-{index}')
            rel.setAttribute('Type', 'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel')
            rels.documentElement.appendChild(rel)
            document = minidom.parseString(mesh_seed)
            mesh_object = document.getElementsByTagName('object')[0]
            mesh_object.setAttribute('id', part_id)
            mesh_object.setAttribute('p:UUID', f'{index:04x}0001-b206-40ff-9872-83e8017abed1')
            for tag, attrs, values in [('vertex', 'xyz', _box(*dimensions, tipped=case == 241)),
                                       ('triangle', ('v1', 'v2', 'v3'), FACES)]:
                for node, row in zip(document.getElementsByTagName(tag), values, strict=True):
                    for axis, value in zip(attrs, row, strict=True):
                        node.setAttribute(axis, str(value))
            dst.writestr(path, document.toxml(encoding='utf-8'))

        replacements = {model_name: model, config_name: config, rels_name: rels}
        for entry in src.infolist():
            if not entry.filename.startswith('3D/Objects/'):
                document = replacements.get(entry.filename)
                dst.writestr(entry, document.toxml(encoding='utf-8') if document else src.read(entry))
