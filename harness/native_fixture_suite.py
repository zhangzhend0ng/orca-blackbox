"""Two fixed cold/shared replay experiments using the native guest runtime."""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from pathlib import Path
import hashlib
import stat
import time
import uuid

from .agent_protocol import ProtocolError, write_json_once
from .native_matrix import REPLAY_SOURCES, UIA_REPLAY_ENUMS, UIA_REPLAY_MOVE_LAYER
from .perf_monitor import launch_phase, set_step
from .run_evidence import RunEvidence
from .run_verdict import CheckResult, aggregate_result, contract_digest
from .runtime_ports import ExecutionOutcome, VerificationOutcome, VerificationSnapshot

FIXTURE_CASES = (UIA_REPLAY_MOVE_LAYER, UIA_REPLAY_ENUMS)


def child_id(batch_id, scenario):
    return uuid.uuid5(uuid.UUID(hex=batch_id), scenario).hex


def verify_initial(raw, fixture, cancelled=lambda: False):
    from .pilot_common import inspect_preserved_settings
    from .project_3mf import _archive, inspect_project
    from .script_verify import _json

    inspect_project(raw, fixture, layer_height="0.4", cancelled=cancelled)
    name = "Metadata/project_settings.config"
    inspect_preserved_settings(_json(_archive(raw, cancelled)[name]),
                               _json(_archive(fixture, cancelled)[name]), cancelled=cancelled)


@dataclass
class FixtureCase:
    scenario: str
    writer: RunEvidence
    root: Path
    receipt: dict
    timing: dict
    ui: object = None
    stopped: int | None = None
    saved_sha: str | None = None


def open_fixture(ui, fixture):
    """Load the immutable run fixture via the exact owned native Open dialog."""
    from .agent_business_ui import _discard_choice

    ui.main_input()
    if not ui.wu.force_set_foreground(ui.app.hwnd):
        raise ProtocolError("fixture_reset_foreground")
    ui._project_command("open project")
    discarded = {}

    def find_dialog():
        matches = []
        for hwnd, pid in ui.wu.enum_windows():
            if pid != ui.app.pid or not ui.owned_dialog(hwnd):
                continue
            caption = ui.wu.window_title(hwnd)
            if caption.rstrip(":") == "Choose one file (3mf)":
                matches.append(hwnd)
                continue
            if caption in discarded:
                continue
            children = ui.eu._children_texts(hwnd)
            if caption == "Snapmaker Orca - Save":
                discard = _discard_choice(caption, children, close_requested=True)
            elif caption.casefold() == "load project: unsaved changes":
                discard = _discard_choice(caption, children)
            else:
                continue
            if discard is None or not ui.owned(discard[2]):
                raise ProtocolError("fixture_reset_discard_identity")
            ui.click_rect(discard[1], root=False, owner=hwnd)
            discarded[caption] = {"dialog_hwnd": hwnd, "button_hwnd": discard[2]}
        if len(matches) > 1:
            raise ProtocolError("fixture_open_ambiguous")
        return matches[0] if matches else None

    dialog = ui.wait(find_dialog, 15)
    field = ui.eu.find_edit(dialog)
    if (not field or not ui.owned(field) or ui.wu.window_class(field) != "Edit"
            or not ui.wu.user32.IsChild(dialog, field)):
        raise ProtocolError("fixture_open_filename_identity")
    ui.guard()
    ui.wu._send_msg(field, 0x00B1, 0, -1)
    ui.wu.msg_text(field, str(fixture))
    if ui.wu.edit_text(field, len(str(fixture)) + 1) != str(fixture):
        raise ProtocolError("fixture_open_filename_readback")
    ui.guard()
    ui.wu._send_msg(dialog, 0x0111, 1, 0)
    ui.wait(lambda: not ui.wu.user32.IsWindow(dialog), 15)
    dismissed = []

    def loaded_fixture():
        for hwnd, pid in ui.wu.enum_windows():
            if (pid == ui.app.pid and hwnd not in dismissed and ui.owned_dialog(hwnd)
                    and ui.wu.window_title(hwnd).casefold() == "customized preset"):
                ui.guard()
                # The same known load blocker is dismissed during cold boot.
                ui.wu.close_window(hwnd)
                dismissed.append(hwnd)
        return (ui.wu.user32.IsWindowEnabled(ui.app.hwnd)
                and fixture.stem in ui.wu.window_title(ui.app.hwnd))

    ui.wait(loaded_fixture, 15)
    return {"dialog_hwnd": dialog, "field_hwnd": field, "at_ns": time.time_ns(),
            "discarded": discarded, "customized_preset_closed_hwnds": dismissed}


def setup_case(case, ui, sut_sha):
    from .agent_guest import _encode_capture
    from .process_panel import advanced_on, advanced_switch, click_tab, ocr_band
    from tools.native_save_guest import atomic_json, bind_native_canvas

    case_root = case.root
    fixture = (case_root / "input/fixture.3mf").read_bytes()
    if not ui.wu.force_set_foreground(ui.app.hwnd):
        raise ProtocolError("fixture_initial_foreground")
    ui.main_input()
    advanced = ui.wait(lambda: advanced_on(ui.app), 8)
    if advanced[1] > advanced[0]:
        switch = advanced_switch(ui.app)
        if not switch or not ui.owned(switch[1]):
            raise ProtocolError("fixture_advanced_owned")
        ui.click_rect(switch[0])
        ui.wait(lambda: (state := advanced_on(ui.app)) and state[0] >= state[1], 8)
    # The existing tab helper resets the process viewport before checking the top group.
    if not click_tab(ui.app, "Quality", "height", timeout_s=15):
        raise ProtocolError("fixture_quality_initial")
    # The disabled bitmap is grayscale. Confirm the simple-mode viewport too:
    # with Advanced enabled its Line width group pushes Seam below the fold.
    words = {word.lower() for word, *_ in ocr_band(ui.app)}
    if not {"seam", "aligned"} <= words:
        raise ProtocolError("fixture_simple_quality_initial")
    witness = copy(ui)
    witness.artifacts = case_root / "initial_state"
    witness.artifacts.mkdir()
    witness.saved = None
    witness.save_project()
    initial_state = witness._project_path().read_bytes()
    verify_initial(initial_state, fixture)
    (case_root / "initial_state.3mf").write_bytes(initial_state)
    case.timing["initial_state_sha256"] = hashlib.sha256(initial_state).hexdigest()
    ui.main_input()
    visible_dialogs = [hwnd for hwnd, pid in ui.wu.enum_windows()
                       if pid == ui.app.pid and ui.owned_dialog(hwnd)]
    if visible_dialogs:
        raise ProtocolError("fixture_initial_owned_dialog")
    if not ui.wu.force_set_foreground(ui.app.hwnd):
        raise ProtocolError("fixture_initial_foreground")
    _, capture = ui.identity()
    initial = _encode_capture(capture)[1]
    (case_root / "initial.png").write_bytes(initial)
    setup = {"run_id": case.writer.run_id, "scenario": case.scenario,
             "app_pid": ui.app.pid, "tab_clicked": "Quality",
             "initial_sha256": hashlib.sha256(initial).hexdigest(),
             "finished_at_ns": time.time_ns()}
    scope = {"run_id": case.writer.run_id, "actor": "script", "scenario": case.scenario,
             "app_pid": ui.app.pid, "hwnd": ui.app.hwnd,
             "contract_sha256": case.receipt["contract_sha256"],
             "output_path": str(case_root / "projects/0001.3mf")}
    bind_native_canvas(ui, scope, case_root, sut_sha)
    atomic_json(case_root / "setup.json", setup)
    atomic_json(case_root / "scope.json", scope)
    case.timing.update(app_pid=ui.app.pid, hwnd=ui.app.hwnd, advanced=False,
                       tab="Quality", owned_dialogs=0, prepared_at_ns=time.time_ns())


def edit_case(case, ui):
    from .agent_guest import _encode_capture
    from .native_uia_replay import play
    from tools.native_save_guest import NativeInput

    native = NativeInput(case.root, case.writer.run_id, ui.guard)
    case.receipt["script_action_started_at_ns"] = time.time_ns()
    started = time.monotonic_ns()
    try:
        native.start()
        case.receipt["recording_sha256"] = play(ui, case.writer.run_id,
            str(case.root / "projects/0001.3mf"), scenario=case.scenario)
        case.receipt["recorded_trace_sha256"] = hashlib.sha256((case.root / "native_trace.ndjson").read_bytes()).hexdigest()
        case.receipt["script_steps"] = ["edit", "save"]
    finally:
        case.receipt["script_action_elapsed_ns"] = time.monotonic_ns() - started
        case.receipt["script_action_finished_at_ns"] = time.time_ns()
        case.stopped = native.stop()
        (case.root / "token").unlink(missing_ok=True)
    case.saved_sha = ui._snapshot()["sha256"]
    (case.root / "agent_final.png").write_bytes(_encode_capture(ui.identity()[1])[1])


def run_fixture_worker(run_id, scenario):
    """The runner's existing guest-native Job and desktop lease enclose the batch."""
    from . import host_guard
    from .agent_guest import REPO, _bytes_once
    from .agent_project_ui import ProjectUI
    from .launcher import default_exe
    from .native_pilots import native_fixture
    from .native_save_session import NATIVE_SUT_SHA256, native_contract
    from .native_matrix import FIXTURE_SCENARIOS
    from tools.native_save_guest import prove_project

    if not host_guard.in_guest() or scenario not in FIXTURE_SCENARIOS:
        raise PermissionError("fixture_guest_only")
    run_id = uuid.UUID(hex=run_id).hex
    root = REPO / "artifacts/v3" / run_id / "artifacts"
    deadline = time.monotonic() + 840

    def guard(local_root=root):
        if (time.monotonic() >= deadline or (root / "control_cancel.json").exists()
                or (local_root / "authority_abort.json").exists()
                or (local_root / "control_cancel.json").exists()):
            raise TimeoutError("fixture_worker_deadline_or_cancel")

    sut_sha = hashlib.sha256(default_exe().read_bytes()).hexdigest()
    if sut_sha != NATIVE_SUT_SHA256:
        raise ProtocolError("native_frozen_sut_changed")
    shared = scenario == "fixture_shared"
    cases = []
    report = {"run_id": run_id, "scenario": scenario, "actor": "script", "release_eligible": False,
              "started_at_ns": time.time_ns(), "cases": [], "error": None, "app_closed": False}
    active = None
    pending = []

    def prove_pending():
        nonlocal active
        if active is None:
            return
        # No reopen or subsequent action is permitted if the MCP is still alive.
        for item in pending:
            if item.stopped is None:
                raise ProtocolError("fixture_input_stop_unconfirmed")
        closing = time.time_ns()
        old = active.app
        active.close()
        if old.popen.poll() != 0:
            raise ProtocolError("fixture_input_app_exit")
        closed = time.time_ns()
        active = None
        for item in pending:
            item.receipt["app_closed"] = True
            item.timing.update(input_close_started_at_ns=closing, input_closed_at_ns=closed)
            if item.receipt["error"] is None:
                item.timing["proof_started_at_ns"] = time.time_ns()
                try:
                    prove_project(item.ui, item.root, item.writer.run_id, item.receipt["contract_sha256"],
                                  item.ui.guard, sut_sha, item.stopped, old, closed, saved_sha=item.saved_sha)
                except Exception as exc:
                    item.receipt["error"] = type(exc).__name__ + ":" + str(exc)[:160]
                finally:
                    item.ui.close()
                item.timing["proof_finished_at_ns"] = time.time_ns()
        pending.clear()

    try:
        for s in FIXTURE_CASES:
            guard()
            contract = native_contract("script", s)
            writer = RunEvidence.create(root.parent.parent, contract, run_id=child_id(run_id, s),
                                        metadata={"environment_id": run_id})
            art = writer.run_dir / "artifacts"
            art.mkdir()
            writer.append_event("runtime_started", status="guest_native")
            receipt = {"run_id": writer.run_id, "actor": "script", "scenario": s,
                       "contract_sha256": contract_digest(contract), "release_eligible": False,
                       "error": None, "app_closed": False, "script_steps": []}
            case = FixtureCase(s, writer, art, receipt,
                               {"run_id": writer.run_id, "scenario": s, "prepare_started_at_ns": time.time_ns()})
            cases.append(case)
            report["cases"].append(case.timing)

            def case_guard(local_root=art):
                guard(local_root)

            try:
                if active is not None:
                    previous = pending[-1]
                    source = previous.root / "input/fixture.3mf"
                    candidate = copy(active)
                    candidate.artifacts, candidate.guard = art, case_guard
                    set_step("fixture_reset", monitor=getattr(candidate.app, "perf", None),
                             case_run_id=writer.run_id)
                    try:
                        case.timing["reopen"] = open_fixture(candidate, source)
                    except Exception as exc:
                        case.timing["reset_error"] = type(exc).__name__ + ":" + str(exc)[:160]
                        case.timing["reset_windows"] = [active.wu.window_title(hwnd)[:128]
                            for hwnd, pid in active.wu.enum_windows() if pid == active.app.pid]
                        for hwnd, pid in active.wu.enum_windows():
                            if pid == active.app.pid and active.owned_dialog(hwnd) and active.wu.window_title(hwnd).casefold() in {
                                "choose one file (3mf):", "choose one file (3mf)", "load project: unsaved changes",
                                "snapmaker orca - save", "customized preset",
                            }:
                                active.wu.close_window(hwnd)
                        active.wait(lambda: active.wu.user32.IsWindowEnabled(active.app.hwnd), 5)
                        prove_pending()
                        case.timing["restart_after_reset_at_ns"] = time.time_ns()
                    else:
                        (art / "input").mkdir()
                        _bytes_once(art / "input/fixture.3mf", source.read_bytes())
                        active = case.ui = candidate
                        case.timing["reused"] = True
                if active is None:
                    with launch_phase("fixture_boot", writer.run_id):
                        active = case.ui = ProjectUI(art, case_guard, fixture=native_fixture(s))
                    case.timing["reused"] = False
                set_step("fixture_edit", monitor=getattr(case.ui.app, "perf", None),
                         case_run_id=writer.run_id)
                (art / "input/fixture.3mf").chmod(stat.S_IREAD)
                (art / "projects").mkdir()
                (art / "proof").mkdir()
                setup_case(case, case.ui, sut_sha)
                edit_case(case, case.ui)
            except Exception as exc:
                receipt["error"] = type(exc).__name__ + ":" + str(exc)[:160]
                # A setup failure never started an MCP; an action failure must have a stopped receipt.
                if "script_action_started_at_ns" not in receipt:
                    case.stopped = time.time_ns()
            if case.ui is not None:
                pending.append(case)
            if not shared or receipt["error"] is not None:
                prove_pending()
        prove_pending()
        report["app_closed"] = True
    except Exception as exc:
        report["error"] = type(exc).__name__ + ":" + str(exc)[:160]
    finally:
        if active is not None:
            try:
                active.close()
                report["app_closed"] = not active.app.alive()
            except Exception as exc:
                report["cleanup_error"] = type(exc).__name__
        for case in cases:
            case.writer.append_event("execution_finished", status="failed" if case.receipt["error"] else "completed")
            write_json_once(case.root / "native_worker.json", case.receipt)
            case.timing.update(error=case.receipt["error"], stopped_at_ns=case.stopped,
                action_elapsed_ns=case.receipt.get("script_action_elapsed_ns"),
                action_started_at_ns=case.receipt.get("script_action_started_at_ns"))
            write_json_once(case.root / "fixture_case.json", {"batch_run_id": run_id, **case.timing})
            case.writer.close()
        report["finished_at_ns"] = time.time_ns()
        write_json_once(root / "fixture_suite.json", report)
    return 0 if report["error"] is None and report["app_closed"] else 1


def verify_fixture_suite(snapshot, scenario, read, cancelled):
    """After Job exit, run each existing business verifier against its own artifacts."""
    from .agent_verify import _require
    from .native_save_session import native_contract, verify_saved
    from .script_verify import _InvalidEvidence, _json, _read

    process = _json(read("process.json", 65536))
    report = _json(read("fixture_suite.json", 65536))
    run_id = snapshot.run_id
    _require(process.get("run_id") == report.get("run_id") == run_id
             and process.get("exit_code") == process.get("active_processes") == 0
             and process.get("job_assigned") is True and process.get("forced_termination") is False
             and report.get("scenario") == scenario and report.get("app_closed") is True
             and report.get("release_eligible") is False and report.get("error") is None,
             "fixture_batch_custody")
    rows = report["cases"]
    _require([row.get("scenario") for row in rows] == list(FIXTURE_CASES), "fixture_case_order")
    verified = []
    proofs = []
    refs = ("artifact:fixture_suite.json", "artifact:process.json")
    for case_scenario, row in zip(FIXTURE_CASES, rows, strict=True):
        ident = child_id(run_id, case_scenario)
        _require(row.get("run_id") == ident, "fixture_child_identity")
        directory = snapshot.artifact_dir.parent.parent / ident
        art = directory / "artifacts"
        _require(not directory.is_symlink() and not art.is_symlink()
                 and directory.resolve(strict=True) == directory and art.resolve(strict=True) == art
                 and all(not (getattr(path.lstat(), "st_file_attributes", 0) & 0x400) for path in (directory, art)),
                 "fixture_child_directory_identity")
        manifest = _json(_read(directory, "manifest.json", 0, 65536, cancelled))
        contract = native_contract("script", case_scenario)
        _require(manifest.get("run_id") == ident and manifest.get("contract_sha256") == contract_digest(contract)
                 and manifest.get("metadata", {}).get("environment_id") == run_id
                 and manifest["started_at_ns"] >= snapshot.manifest["started_at_ns"],
                 "fixture_child_contract")
        child_read = lambda name, size: _read(art, name, manifest["started_at_ns"], size, cancelled)
        status = "failed" if row.get("error") else "completed"
        outcome = VerificationOutcome({}, False, False)
        try:
            _require(_json(child_read("fixture_case.json", 65536)) == {"batch_run_id": run_id, **row},
                     "fixture_case_receipt")
            if status == "completed":
                witness = child_read("initial_state.3mf", 16*1024*1024)
                fixture = child_read("input/fixture.3mf", 16*1024*1024)
                _require(row.get("initial_state_sha256") == hashlib.sha256(witness).hexdigest()
                         and row.get("advanced") is False and row.get("tab") == "Quality"
                         and row.get("owned_dialogs") == 0, "fixture_initial_state_receipt")
                verify_initial(witness, fixture, cancelled)
                proof = _json(child_read("proof.json", 65536))
                _require(proof["old_pid"] == row["app_pid"] and proof["old_pid"] != proof["reopened_pid"]
                         and proof["old_closed_at_ns"] == row["input_closed_at_ns"],
                         "fixture_case_custody")
                phases = [manifest["started_at_ns"], row["prepare_started_at_ns"], row["prepared_at_ns"],
                          row["action_started_at_ns"], row["stopped_at_ns"], row["input_close_started_at_ns"],
                          row["input_closed_at_ns"], row["proof_started_at_ns"], row["proof_finished_at_ns"]]
                _require(phases == sorted(phases) and phases[-1] <= report["finished_at_ns"]
                         and proof["input_stopped_at_ns"] == row["stopped_at_ns"]
                         and proof["mcp_active_processes"] == 0, "fixture_case_phase_order")
                child = VerificationSnapshot(contract, ident, art, manifest, ExecutionOutcome(status))
                outcome = verify_saved(child, cancelled=cancelled, batch_process=process)
                proofs.append(proof)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            detail = str(exc) if isinstance(exc, _InvalidEvidence) else "fixture_case_evidence_unavailable"
            outcome = VerificationOutcome({"path": CheckResult("unknown", detail)}, False, False)
        result = aggregate_result(contract, status, outcome.checks, evidence_complete=outcome.evidence_complete,
                                  execution_compliant=outcome.execution_compliant).to_dict()
        passed = result["verified_pass"]
        result.update(mode="script_shadow", release_verdict="SHADOW" if passed else "NON_GREEN",
                      release_eligible=False, cleanup_confirmed=True, runtime_status=status,
                      batch_run_id=run_id, gui_execution_requested=True)
        write_json_once(directory / "result.json", result)
        verified.append(passed)
        refs += ("run:" + ident + ":result.json",)

    if not all(verified):
        return VerificationOutcome({"business": CheckResult("fail", f"{sum(verified)}/{len(rows)} independent checks passed", refs)},
                                   False, False)
    first, second = rows
    same_app = (first["app_pid"], first["hwnd"]) == (second["app_pid"], second["hwnd"])
    shared = scenario == "fixture_shared"
    reuse_proven = (first["reused"] is False and second["reused"] is True and same_app
                    and second.get("reopen", {}).get("at_ns", 0) >= first["stopped_at_ns"]
                    and "reset_error" not in second
                    and first["input_closed_at_ns"] == second["input_closed_at_ns"])
    cold_proven = (first["reused"] is False and second["reused"] is False and not same_app
                   and second["prepare_started_at_ns"] >= first["proof_finished_at_ns"])
    proof_isolation = (first["proof_finished_at_ns"] <= second["proof_started_at_ns"]
                       and proofs[0]["reopened_pid"] != proofs[1]["reopened_pid"])
    path_ok = (reuse_proven if shared else cold_proven) and proof_isolation
    return VerificationOutcome({
        "path": CheckResult("pass" if path_ok else "fail",
                            "Expected editing-session custody and serial independent reopens"
                            if path_ok else "Requested fixture mode or independent reopen ordering was not proven", refs),
        "business": CheckResult("pass", "Both child project and G-code checks passed", refs),
    }, path_ok, path_ok)
