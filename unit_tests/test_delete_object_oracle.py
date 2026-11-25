from pathlib import Path
import sys
from xml.dom import minidom
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from delete_object_oracle import create_fixture, verify_sequence


def test_only_the_selected_object_may_be_removed_and_restored(tmp_path):
    initial = tmp_path / 'before.3mf'
    create_fixture(ROOT / 'fixtures/feishu_std_cubesfar.3mf', initial)
    deleted = tmp_path / 'deleted.3mf'
    with ZipFile(initial) as src, ZipFile(deleted, 'w') as dst:
        for entry in src.infolist():
            data = src.read(entry)
            if entry.filename in ('3D/3dmodel.model', 'Metadata/model_settings.config'):
                doc = minidom.parseString(data)
                tags = ('item',) if entry.filename.endswith('.model') else ('object', 'model_instance')
                for tag in tags:
                    node = doc.getElementsByTagName(tag)[0]
                    node.parentNode.removeChild(node)
                data = doc.toxml(encoding='utf-8')
            dst.writestr(entry, data)
    bounds = verify_sequence(initial, deleted, initial)
    assert bounds['Alpha'][0] == [75, 95]
    assert bounds['Bravo'][0] == [177, 193]
    with pytest.raises(ValueError):
        verify_sequence(initial, initial, initial)
    with pytest.raises(ValueError):
        verify_sequence(initial, deleted, deleted)
