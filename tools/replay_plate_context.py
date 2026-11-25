"""Recheck retained #239 and #243 plate images and physical project geometry."""
from pathlib import Path
import json
import sys

from tools.replay_evidence_files import verified_part
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from delete_object_oracle import objects


def _reader(directory, prefix):
    manifest = json.loads((directory / f'{prefix}-object_artifacts.json').read_text(encoding='utf-8-sig'))
    return lambda name: verified_part(directory, prefix, manifest, name)


def replay_delete_all(directory: Path, prefix: str) -> dict:
    from PIL import Image
    read = _reader(directory, prefix)
    initial = objects(read('before.3mf'))
    analysis = json.loads(read('analysis.json').read_text(encoding='utf-8'))
    centers = analysis['centers']
    if len(centers) != 2 or abs(centers[0][0] - centers[1][0]) < 80:
        raise ValueError('expected two distinct viewport sample positions')
    counts = {}
    for phase in ('before','empty','restored'):
        with Image.open(read(phase + '.png')) as image:
            counts[phase] = []
            for x,y in centers:
                if not (12 <= x <= image.width-12 and 12 <= y <= image.height-12):
                    raise ValueError('sample outside capture')
                patch = image.convert('RGB').crop((x-12,y-12,x+12,y+12))
                pixels = patch.load()
                observed = [pixels[col, row] for row in range(patch.height) for col in range(patch.width)]
                counts[phase].append(sum(max(rgb) - min(rgb) > 45 for rgb in observed))
    return {'checks': {'two_fixture_meshes_loaded': set(initial) == {'Alpha','Bravo'} and initial == objects(read('Alpha-Bravo.3mf')),
                       'both_objects_removed_from_view': min(counts['before']) >= 200 and max(counts['empty']) <= 30,
                       'both_meshes_restored_in_place': initial == objects(read('restored.3mf')) and min(counts['restored']) >= 200},
            'viewport_counts': counts}

def replay_add_primitive(directory: Path, prefix: str) -> dict:
    read = _reader(directory, prefix)
    first, second = objects(read('cube.3mf')), objects(read('edited.3mf'))
    if len(first) != 1 or set(first) != set(second):
        raise ValueError('expected the same single cube before and after the edit')
    name = next(iter(first))
    faces = first[name]
    coords = [{v[i] for face in faces for v in face} for i in range(3)]
    sizes = [max(axis)-min(axis) for axis in coords]
    planes = [sum(all(v[i] == value for v in face) for face in faces) for i,axis in enumerate(coords) for value in axis]
    translated = tuple(tuple((round(x+10,5),y,z) for x,y,z in face) for face in faces)
    return {'checks': {'new_cube_distinct_from_template': name == 'Cube' and name not in objects(read('new-project.3mf')),
                       'closed_six_square_faces_on_plate': len(faces) == 12 and all(len(axis)==2 for axis in coords)
                       and len(set(sizes)) == 1 and sizes[0] > 0 and min(coords[2]) == 0 and planes == [2]*6,
                       'actual_10_mm_cube_edit': second[name] == translated}, 'edge_mm': sizes}
