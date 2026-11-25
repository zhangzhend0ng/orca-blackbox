"""#244 checks use a harvested cube and explicit wrong-file/geometry controls."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from import_model_oracle import verify_import


ARCHIVES = ROOT / 'docs/runs/evidence/feishu-250-251-2026-11-25/row-251-hyperv'


@pytest.mark.parametrize('model,profile,valid', [
    ('Snapmaker U1', 'Snapmaker U1 (0.8 nozzle)', True),
    ('', 'Default Printer', False),
    ('', 'Snapmaker U1 (0.8 nozzle)', False),
    ('Snapmaker U1', 'Default Printer', False),
])
def test_import_requires_requested_mesh_size_and_filename(tmp_path, model, profile, valid):
    original = ARCHIVES / 'a7a65272-before-reload.3mf'
    cube = ARCHIVES / 'a7a65272-source-20mm.stl'
    with pytest.raises(ValueError, match='source'):
        verify_import(original, cube)
    renamed = tmp_path / 'imported.3mf'
    with ZipFile(original) as raw, ZipFile(renamed, 'w') as out:
        for entry in raw.infolist():
            data = raw.read(entry)
            if entry.filename == 'Metadata/model_settings.config':
                data = data.replace(b'reload_cube.stl', b'cube_20mm.stl')
            if entry.filename == 'Metadata/project_settings.config':
                settings = json.loads(data)
                settings.update(printer_model=model, printer_settings_id=profile)
                data = json.dumps(settings).encode('utf-8')
            out.writestr(entry, data)
    if not valid:
        with pytest.raises(ValueError, match='printer'):
            verify_import(renamed, cube)
        return
    assert verify_import(renamed, cube)['dimensions_mm'] == [20, 20, 20]
    with pytest.raises(ValueError, match='facets'):
        verify_import(renamed, ARCHIVES / 'a7a65272-source-30mm.stl')
