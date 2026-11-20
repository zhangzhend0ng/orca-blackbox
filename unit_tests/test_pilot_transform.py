"""Synthetic counterexamples only; no GUI or model coverage."""
from decimal import Decimal
import io
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pytest

from harness.agent_protocol import LAYER_FIXTURE
from harness.pilot_transform import verify_business
from harness.project_3mf import _CORE


def project(dx=10, dy=0, dz=0, *, shape=False, scale=False, setting=False, assembly=False):
    with zipfile.ZipFile(io.BytesIO(Path(LAYER_FIXTURE).read_bytes())) as archive:
        files = {n:archive.read(n) for n in archive.namelist()}
    name = "3D/3dmodel.model"
    root = ET.fromstring(files[name])
    item = root.find(_CORE+"build/"+_CORE+"item")
    matrix = list(map(Decimal,item.get("transform").split()))
    for i,delta in enumerate((dx,dy,dz),9): matrix[i] += Decimal(str(delta))
    if scale: matrix[0] = Decimal("1.01")
    text = " ".join(map(str,matrix));item.set("transform",text)
    files[name] = ET.tostring(root)
    name = "Metadata/model_settings.config"
    root = ET.fromstring(files[name])
    if assembly: root.find("assemble/assemble_item").set("transform",text)
    files[name] = ET.tostring(root)
    if shape:
        name = next(n for n in files if n.startswith("3D/Objects/") and n.endswith(".model"))
        root = ET.fromstring(files[name]);v=root.find(".//"+_CORE+"vertex");v.set("x",str(Decimal(v.get("x"))+1))
        files[name] = ET.tostring(root)
    if setting:
        name="Metadata/project_settings.config";c=json.loads(files[name]);c["wall_loops"]="3";files[name]=json.dumps(c).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items():archive.writestr(name,data)
    return out.getvalue()


def moves(dx=10, *, positive=True, layer="0.4", tiny=False):
    lo=Decimal("122.4")+Decimal(dx);hi=Decimal("148.6")+Decimal(dx)
    if tiny:hi=lo+1
    e="1" if positive else "0"
    lines=["; EXECUTABLE_BLOCK_START","G90","M83","T0","G92 E0"]
    z=Decimal("0.4")
    while z<Decimal(27)+Decimal(layer):
        lines += [f"G1 X{lo} Y122.9 Z{z}","EXCLUDE_OBJECT_START NAME=cube",
            f"G1 X{hi} Y122.9 E{e}",f"G1 X{hi} Y149.1 E{e}",
            f"G1 X{lo} Y149.1 E{e}",f"G1 X{lo} Y122.9 E{e}","EXCLUDE_OBJECT_END NAME=cube"]
        z += Decimal(layer)
    lines += ["; EXECUTABLE_BLOCK_END","; CONFIG_BLOCK_START",f"; layer_height = {layer}",
              "; first_layer_height = 0.4","; CONFIG_BLOCK_END",""]
    return "\n".join(lines).encode()


def verify(raw=None, gcode=None):
    return verify_business(project() if raw is None else raw,Path(LAYER_FIXTURE).read_bytes(),moves() if gcode is None else gcode)


def test_shifted_geometry_and_actual_moved_extrusion_are_both_required():
    result=verify()
    assert result["translation_x_mm"]=="10" and result["project"]["shape_preserved"]
    assert result["gcode"]["layer_count"]==68
    assert result["other_fixture_settings_preserved"] is True


@pytest.mark.parametrize("kwargs", [{"dx":0},{"dx":-10},{"dx":9.9},{"dx":0,"dy":10},
    {"dz":1},{"shape":True},{"scale":True},{"setting":True},{"assembly":True}])
def test_wrong_transform_or_unrelated_mutation_is_rejected(kwargs):
    with pytest.raises(ValueError):verify(project(**kwargs))


@pytest.mark.parametrize("kwargs", [{"dx":0},{"dx":-10},{"positive":False},{"layer":"0.24"},{"tiny":True}])
def test_stale_wrong_placement_or_fake_gcode_is_rejected(kwargs):
    with pytest.raises(ValueError):verify(gcode=moves(**kwargs))


def test_forged_comment_only_gcode_is_rejected():
    with pytest.raises(ValueError):verify(gcode=b"; layer_height = 0.4\n; first_layer_height = 0.4\n")


def test_fixture_identity_is_not_an_agent_supplied_expected_value():
    with pytest.raises(ValueError,match="fixture_identity"):
        verify_business(project(),project(),moves())
