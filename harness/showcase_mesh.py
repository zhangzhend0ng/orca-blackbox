"""Build a repeatable dense single-plate 3MF from the existing U1 fixture."""

from copy import deepcopy
import math
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
MAIN = "3D/3dmodel.model"
SETTINGS = "Metadata/model_settings.config"
RELS = "3D/_rels/3dmodel.model.rels"
SIDES, LEVELS = 288, 112
PLACEMENTS = ((52, 77), (136, 77), (220, 77), (52, 182), (136, 182), (220, 182))


def _tag(name):
    return f"{{{CORE}}}{name}"


def _uuid(label):
    return str(uuid5(NAMESPACE_URL, "orca-blackbox/perf-showcase/" + label))


def _mesh(root, index, height):
    mesh = root.find(f".//{_tag('mesh')}")
    vertices, triangles = list(mesh)
    vertices.clear()
    triangles.clear()
    angles = [math.tau * j / SIDES for j in range(SIDES)]
    for ring in range(LEVELS + 1):
        frac = ring / LEVELS
        z = (frac - .5) * height
        for angle in angles:
            radial = (26 - 4 * frac + 2 * math.sin(frac * math.tau)
                      + 1.7 * math.cos((7 + index) * angle + frac * math.tau * .7))
            ET.SubElement(vertices, _tag("vertex"), x=f"{radial * math.cos(angle):.5f}",
                          y=f"{radial * math.sin(angle):.5f}", z=f"{z:.5f}")
    bottom_center = (LEVELS + 1) * SIDES
    ET.SubElement(vertices, _tag("vertex"), x="0", y="0", z=f"{-height / 2:.5f}")
    ET.SubElement(vertices, _tag("vertex"), x="0", y="0", z=f"{height / 2:.5f}")

    def face(a, b, c):
        ET.SubElement(triangles, _tag("triangle"), v1=str(a), v2=str(b), v3=str(c))

    for j in range(SIDES):
        following = (j + 1) % SIDES
        face(bottom_center, following, j)
        face(bottom_center + 1, LEVELS * SIDES + j, LEVELS * SIDES + following)
        for ring in range(LEVELS):
            a, b = ring * SIDES + j, ring * SIDES + following
            face(a, b, b + SIDES)
            face(a, b + SIDES, a + SIDES)
    return len(triangles)


def build_dense_plate(template: Path, output: Path):
    ET.register_namespace("", CORE)
    ET.register_namespace("p", PROD)
    with ZipFile(template) as source, ZipFile(output, "x", ZIP_DEFLATED, compresslevel=4) as target:
        model = ET.fromstring(source.read(MAIN))
        settings = ET.fromstring(source.read(SETTINGS))
        resources, build = model.find(_tag("resources")), model.find(_tag("build"))
        obj, item = resources[0], build[0]
        component = obj.find(f".//{_tag('component')}")
        original_mesh = component.attrib[f"{{{PROD}}}path"].lstrip("/")
        template_mesh = source.read(original_mesh)
        plate, assemble = settings.find("plate"), settings.find("assemble")
        config_obj, instance, assembled = settings.find("object"), plate.find("model_instance"), assemble[0]
        resources.remove(obj)
        build.remove(item)
        settings.remove(config_obj)
        plate.remove(instance)
        assemble.remove(assembled)
        relations = ET.Element("Relationships", xmlns=REL)
        faces = 0
        for index, (x, y) in enumerate(PLACEMENTS, 1):
            name, object_id = f"Ribbed tower {index}", str(10 + index)
            height = 36 + index * 4
            transform = f"1 0 0 0 1 0 0 0 1 {x} {y} {height / 2}"
            path = f"3D/Objects/tower_{index}.model"
            new_obj, new_item = deepcopy(obj), deepcopy(item)
            new_obj.attrib.update(id=object_id)
            new_obj.set(f"{{{PROD}}}UUID", _uuid(f"object-{index}"))
            new_component = new_obj.find(f".//{_tag('component')}")
            new_component.set(f"{{{PROD}}}path", "/" + path)
            new_component.set(f"{{{PROD}}}UUID", _uuid(f"component-{index}"))
            new_item.attrib.update(objectid=object_id, transform=transform)
            new_item.set(f"{{{PROD}}}UUID", _uuid(f"item-{index}"))
            resources.append(new_obj)
            build.append(new_item)

            new_config = deepcopy(config_obj)
            new_config.set("id", object_id)
            for entry in new_config.findall(".//metadata[@key='name']"):
                entry.set("value", name)
            settings.insert(index - 1, new_config)
            new_instance = deepcopy(instance)
            new_instance.find("metadata[@key='object_id']").set("value", object_id)
            new_instance.find("metadata[@key='identify_id']").set("value", str(90 + index))
            plate.append(new_instance)
            new_assembly = deepcopy(assembled)
            new_assembly.attrib.update(object_id=object_id, transform=transform)
            assemble.append(new_assembly)

            mesh = ET.fromstring(template_mesh)
            mesh.find(f".//{_tag('object')}").set(f"{{{PROD}}}UUID", _uuid(f"mesh-{index}"))
            faces += _mesh(mesh, index, height)
            target.writestr(path, ET.tostring(mesh, encoding="utf-8", xml_declaration=True))
            ET.SubElement(relations, "Relationship", Target="/" + path, Id=f"rel-{index}",
                          Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel")
        for name in source.namelist():
            if name not in {MAIN, SETTINGS, RELS, original_mesh}:
                target.writestr(name, source.read(name))
        for name, node in ((MAIN, model), (SETTINGS, settings), (RELS, relations)):
            target.writestr(name, ET.tostring(node, encoding="utf-8", xml_declaration=True))
    return faces
