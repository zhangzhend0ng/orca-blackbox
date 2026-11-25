"""Offline disk evidence for Feishu #244 Add Models."""
import json
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from harness.model_move_pilot import stl_mesh
from part_attachment_oracle import _facets, _load_project


def verify_import(project: Path, source: Path) -> dict:
    saved = _load_project(project, 1)
    part, = saved.parts
    if part.shape != _facets(*stl_mesh(source.read_bytes())):
        raise ValueError("saved facets differ from the input cube")
    dimensions = [high - low for low, high in part.world_bounds]
    if any(abs(value - 20) > 0.0001 for value in dimensions):
        raise ValueError(f"expected 20 mm on each axis, got {dimensions}")
    with ZipFile(project) as z:
        config = ET.fromstring(z.read('Metadata/model_settings.config'))
        settings = json.loads(z.read('Metadata/project_settings.config'))
    source_field = config.find("./object/part/metadata[@key='source_file']")
    recorded = PureWindowsPath(source_field.get('value', '')) if source_field is not None else None
    if recorded is None or recorded.name != 'cube_20mm.stl':
        raise ValueError(f"unexpected imported source: {recorded}")
    printer = settings.get('printer_settings_id')
    if not isinstance(printer, str) or not printer.strip():
        raise ValueError("saved project lacks the selected printer")
    if len(config.findall('plate')) != 1:
        raise ValueError("expected a single current plate")
    return {'source_file': str(recorded), 'dimensions_mm': dimensions, 'printer': printer,
            'triangles': len(part.shape), 'printable_object_id': saved.object_id}
