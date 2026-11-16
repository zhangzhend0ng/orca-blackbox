"""Save/reopen/reslice evidence challenges. All data is synthetic; no GUI."""
import copy
import hashlib
import io
import json
from pathlib import Path
import threading
import zipfile

import pytest

from harness.agent_layer_verify import request_digest
from harness.agent_project_verify import AgentProjectVerifier, verify_project
from harness.agent_session import agent_contract
from harness.project_3mf import inspect_project
from harness.run_verdict import contract_digest
from harness.runtime_ports import Done, Pending
from unit_tests.test_agent_layer_verify import evidence, gcode, persist, write_json


def project_bytes(fixture, mutate=None):
    with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
        members = {i.filename: archive.read(i) for i in archive.infolist()}
    cfg = json.loads(members["Metadata/project_settings.config"])
    cfg["layer_height"] = "0.24"
    members["Metadata/project_settings.config"] = json.dumps(cfg).encode()
    if mutate:
        mutate(members)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return output.getvalue()


@pytest.fixture
def project_evidence(evidence):
    snapshot, trace, receipts = evidence
    root = snapshot.artifact_dir
    snapshot.contract = agent_contract("m3g_export_3mf")
    (root / "projects").mkdir()
    raw = project_bytes((root / "input/fixture.3mf").read_bytes())
    (root / "projects/0001.3mf").write_bytes(raw)
    (root / "exports/0001.gcode").write_bytes(gcode("0.24"))
    methods = ("observe", "edit", "save_project", "reopen_project", "slice", "export_gcode", "finish")
    for seq, (pair, method) in enumerate(zip(trace, methods), 1):
        pair["request"].update(method=method, arguments={"x": 250, "y": 90, "text": "0.24"} if method == "edit" else {})
        pair["response"]["tool"] = method
        if seq >= 4:
            pair["response"]["observation"]["window"].update(pid=201, hwnd=301)
    details = [None, {"target_hwnd": 600, "control_class": "Edit", "before_text": "0.4", "after_text": "0.24"},
        {"dialog_hwnd": 700, "edit_hwnd": 800, "path": "projects/0001.3mf", "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)},
        {"path": "projects/0001.3mf", "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "datadir": "profile_reopen",
         "old_pid": 200, "old_hwnd": 300, "old_exit_code": 0, "old_closed_at_ns": 38_100_000_000,
         "new_pid": 201, "new_hwnd": 301, "new_started_at_ns": 38_500_000_000, "driver_pid": 100},
        {"button_hwnd": 500, "done_observed": True}]
    final = (root / "exports/0001.gcode").read_bytes()
    details.append({"dialog_hwnd": 700, "edit_hwnd": 800, "path": "exports/0001.gcode", "sha256": hashlib.sha256(final).hexdigest(), "size_bytes": len(final)})
    for item in receipts[1:]:
        seq = item["seq"]
        item.update(method=methods[seq - 1], request_sha256=request_digest(trace[seq - 1]["request"]), details=details[seq - 1])
        if seq >= 4:
            item["window"].update(pid=201, hwnd=301)
    for name in ("process.json", "agent_report.json"):
        data = json.loads((root / name).read_text())
        data["case_id"] = snapshot.contract.case_id
        if name == "agent_report.json":
            data.update(app_pid=201, hwnd=301)
        write_json(root / name, data)
    write_json(root / "ready.json", {"schema_version": 1, "case_id": snapshot.contract.case_id, "run_id": snapshot.run_id,
        "driver_pid": 100, "app_pid": 200, "hwnd": 300, "contract_sha256": contract_digest(snapshot.contract)})
    persist(snapshot, trace, receipts)
    return snapshot, trace, receipts


def replace_saved(snapshot, receipts, raw):
    (snapshot.artifact_dir / "projects/0001.3mf").write_bytes(raw)
    for item in receipts:
        if item["method"] in ("save_project", "reopen_project"):
            item["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))


def test_whole_project_chain_passes_only_with_persistence_and_actual_reslice(project_evidence):
    snapshot, *_ = project_evidence
    result = verify_project(snapshot)
    assert result.evidence_complete and result.execution_compliant
    assert result.checks["path"].status == result.checks["business"].status == "pass"


def test_fault_audit_can_inspect_unchanged_point_four_without_weakening_default(project_evidence):
    snapshot, *_ = project_evidence
    fixture = (snapshot.artifact_dir / "input/fixture.3mf").read_bytes()
    with pytest.raises(ValueError, match="project_layer_config"):
        inspect_project(fixture, fixture)
    assert inspect_project(fixture, fixture, layer_height="0.4")["geometry_unchanged"]


@pytest.mark.parametrize("printer,accepted", [
    ("Snapmaker U1 (0.8 nozzle)(fixture.3mf)", True),
    ("Snapmaker U1 (0.8 nozzle)(another.3mf)", False),
    ("Snapmaker U1 (0.8 nozzle)(fixture.3mf)(0001.3mf)", False),
    ("Snapmaker U1 (0.4 nozzle)(fixture.3mf)", False),
    ("Snapmaker U1 (0.8 nozzle)-1(fixture.3mf)", False),
    ("Snapmaker U1 (0.8 nozzle)(fixture.3mf)extra", False)])
def test_only_exact_fixed_fixture_printer_alias_is_accepted(project_evidence, printer, accepted):
    snapshot, trace, receipts = project_evidence
    def change(members):
        name = "Metadata/project_settings.config"
        config = json.loads(members[name]); config["printer_settings_id"] = printer
        members[name] = json.dumps(config).encode()
    raw = project_bytes((snapshot.artifact_dir / "input/fixture.3mf").read_bytes(), change)
    replace_saved(snapshot, receipts, raw); persist(snapshot, trace, receipts)
    result = verify_project(snapshot)
    assert result.evidence_complete is accepted
    if not accepted:
        assert result.checks["business"].detail == "project_slicing_scope"


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("size_bytes", 1), ("datadir", "profile"),
    ("old_exit_code", True), ("old_exit_code", 1), ("old_pid", 999), ("new_pid", 999),
    ("driver_pid", 999), ("new_started_at_ns", 1), ("old_closed_at_ns", 40_000_000_000)])
def test_reopen_requires_same_saved_file_fresh_profile_and_old_instance_exit(project_evidence, field, value):
    snapshot, trace, receipts = project_evidence
    receipts[3]["details"][field] = value
    persist(snapshot, trace, receipts)
    assert not verify_project(snapshot).evidence_complete


@pytest.mark.parametrize("seq", [1, 3, 4, 5, 7])
def test_identity_changes_are_allowed_only_at_the_unique_reopen_boundary(project_evidence, seq):
    snapshot, trace, receipts = project_evidence
    trace[seq - 1]["response"]["observation"]["window"]["pid"] = 999
    persist(snapshot, trace, receipts)
    assert verify_project(snapshot).checks["path"].status != "pass"


def test_omitting_explicit_slice_does_not_pass_even_with_valid_final_gcode(project_evidence):
    snapshot, trace, receipts = project_evidence
    trace[4]["request"].update(method="observe", arguments={}); trace[4]["response"]["tool"] = "observe"
    persist(snapshot, trace, receipts)
    result = verify_project(snapshot)
    assert result.checks["path"].detail == "operation_order" and not result.evidence_complete


def mutate_member(members, name, old, new):
    members[name] = members[name].replace(old, new, 1)


@pytest.mark.parametrize("mutation", ["regular", "first", "geometry", "build", "paint", "override", "variable", "entity", "path", "bad-number"])
def test_saved_project_semantics_are_independently_checked(project_evidence, mutation):
    snapshot, trace, receipts = project_evidence
    def change(members):
        if mutation in ("regular", "first", "bad-number"):
            name = "Metadata/project_settings.config"; cfg = json.loads(members[name])
            cfg["initial_layer_print_height" if mutation == "first" else "layer_height"] = "0.24" if mutation == "first" else "NaN" if mutation == "bad-number" else "0.4"
            members[name] = json.dumps(cfg).encode()
        elif mutation == "geometry":
            name = next(x for x in members if x.startswith("3D/Objects/")); mutate_member(members, name, b'x="13.5"', b'x="14.5"')
        elif mutation == "build":
            mutate_member(members, "3D/3dmodel.model", b'135.5 136 13.5', b'136.5 136 13.5')
        elif mutation == "paint":
            name = next(x for x in members if x.startswith("3D/Objects/")); mutate_member(members, name, b'<triangle ', b'<triangle paint_color="1" ')
        elif mutation == "override":
            mutate_member(members, "Metadata/model_settings.config", b'<part ', b'<metadata key="layer_height" value="0.4"/><part ')
        elif mutation == "variable":
            members["Metadata/layer_heights_profile.txt"] = b"object_id=2|0;0.4;27;0.4\n"
        elif mutation == "entity":
            members["Metadata/model_settings.config"] = b'<!DOCTYPE config [<!ENTITY x "a">]><config>&x;</config>'
        else:
            members["../escaped.xml"] = b"x"
    raw = project_bytes((snapshot.artifact_dir / "input/fixture.3mf").read_bytes(), change)
    replace_saved(snapshot, receipts, raw); persist(snapshot, trace, receipts)
    result = verify_project(snapshot)
    assert result.checks["path"].status == "pass"
    assert result.checks["business"].status != "pass" and not result.evidence_complete


@pytest.mark.parametrize("raw", [b"not zip", b"PK\x03\x04", b""])
def test_corrupt_project_does_not_escape_the_worker_or_prove_business(project_evidence, raw):
    snapshot, trace, receipts = project_evidence
    replace_saved(snapshot, receipts, raw); persist(snapshot, trace, receipts)
    assert not verify_project(snapshot).evidence_complete


def test_saved_config_and_ui_receipts_do_not_prove_reopened_slicing(project_evidence):
    snapshot, trace, receipts = project_evidence
    raw = gcode()
    (snapshot.artifact_dir / "exports/0001.gcode").write_bytes(raw)
    receipts[-1]["details"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    persist(snapshot, trace, receipts)
    result = verify_project(snapshot)
    assert result.checks["path"].status == "pass" and result.checks["business"].status == "fail"


@pytest.mark.parametrize("method", ["observe", "click"])
def test_extra_observation_action_moves_reopen_boundary_instead_of_hardcoding_seq_four(project_evidence, method):
    snapshot, trace, receipts = project_evidence
    extra = copy.deepcopy(trace[2]); extra["request"].update(method=method, arguments={"x": 200, "y": 45} if method == "click" else {}); extra["response"]["tool"] = method
    for i, frame in enumerate(extra["response"]["observation"]["frames"]):
        frame["captured_at_ns"] = 35_000_000_000 + i * 1_000_000_000
    trace.insert(3, extra)
    root = snapshot.artifact_dir
    for seq, pair in enumerate(trace, 1):
        req, res = pair["request"], pair["response"]
        req.update(seq=seq, observation_id=None if seq == 1 else f"{snapshot.run_id}_{seq-1:04d}"); res["seq"] = seq
        obs = res["observation"]; obs["id"] = f"{snapshot.run_id}_{seq:04d}"
        for i, frame in enumerate(obs["frames"]):
            raw = (root / frame["path"]).read_bytes()
            frame["path"] = f"frames/{seq:04d}_{'ab'[i]}.bmp"; (root / frame["path"]).write_bytes(raw)
        raw = (root / obs["image"]["path"]).read_bytes()
        obs["image"]["path"] = f"frames/{seq:04d}.png"; (root / obs["image"]["path"]).write_bytes(raw)
    for item in receipts[1:]:
        if item["seq"] >= 4: item["seq"] += 1
        item["request_sha256"] = request_digest(trace[item["seq"] - 1]["request"])
    report = json.loads((root / "agent_report.json").read_text()); report.update(calls=8, clicks=1 if method == "click" else 0); write_json(root / "agent_report.json", report)
    persist(snapshot, trace, receipts)
    assert verify_project(snapshot).evidence_complete


def test_reused_pid_and_hwnd_numbers_still_require_old_exit_and_new_launch_receipt(project_evidence):
    snapshot, trace, receipts = project_evidence
    for pair in trace[3:]:
        pair["response"]["observation"]["window"].update(pid=200, hwnd=300)
    for receipt in receipts[3:]:
        receipt["window"].update(pid=200, hwnd=300)
    receipts[3]["details"].update(new_pid=200, new_hwnd=300)
    path = snapshot.artifact_dir / "agent_report.json"
    report = json.loads(path.read_text()); report.update(app_pid=200, hwnd=300); write_json(path, report)
    persist(snapshot, trace, receipts)
    assert verify_project(snapshot).evidence_complete


def test_project_worker_is_read_only_daemon_and_cleanup_waits_for_actual_stop(project_evidence, monkeypatch):
    import harness.agent_project_verify as module
    snapshot, *_ = project_evidence
    release = threading.Event(); original = module.verify_project
    def blocked(s, **kwargs):
        release.wait(5); return original(s, **kwargs)
    monkeypatch.setattr(module, "verify_project", blocked)
    handle = AgentProjectVerifier().start(snapshot)
    try:
        assert handle.worker.daemon and isinstance(handle.poll(), Pending)
        handle.cancel("timeout"); assert isinstance(handle.start_cleanup().poll(), Pending)
    finally:
        release.set(); handle.worker.join(5)
    assert isinstance(handle.start_cleanup().poll(), Done) and not handle.poll().value.evidence_complete
