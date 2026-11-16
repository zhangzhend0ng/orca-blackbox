"""CLI checks use only temporary files; they never launch Orca."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts" / "examples" / "m0_boot_check.json"


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools" / "v3_session.py"), *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def test_validate_does_not_create_run_directory(tmp_path):
    result = invoke("validate", EXAMPLE, "--root", tmp_path / "runs")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "valid", "case_id": "m0_boot_check"}
    assert not (tmp_path / "runs").exists()


def test_init_creates_distinct_unfinished_runs(tmp_path):
    first = invoke("init", EXAMPLE, "--root", tmp_path)
    second = invoke("init", EXAMPLE, "--root", tmp_path)
    assert first.returncode == second.returncode == 0, (first.stderr, second.stderr)
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    assert a["run_id"] != b["run_id"]
    for result in (a, b):
        directory = Path(result["run_dir"])
        assert directory.parent == tmp_path
        assert result["gui_executed"] is False
        assert (directory / "manifest.json").is_file()
        assert not (directory / "result.json").exists()


def test_invalid_input_does_not_echo_payload_or_create_run(tmp_path):
    contract = tmp_path / "invalid.json"
    contract.write_text('{"private":"do-not-echo-this",}', encoding="utf-8")
    result = invoke("init", contract, "--root", tmp_path / "runs")
    assert result.returncode == 2
    assert json.loads(result.stderr)["status"] == "error"
    assert "do-not-echo-this" not in result.stderr + result.stdout
    assert not (tmp_path / "runs").exists()


def test_smoke_runs_complete_lifecycle_without_claiming_gui_or_release(tmp_path):
    result = invoke("smoke", "--root", tmp_path)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["verified_pass"] is True
    assert value["mode"] == "synthetic"
    assert value["gui_executed"] is False
    assert value["release_eligible"] is False
    assert "GREEN" not in result.stdout
    directory = Path(value["run_dir"])
    assert (directory / "manifest.json").is_file()
    assert (directory / "events.ndjson").is_file()
    saved = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "synthetic"
    assert saved["release_eligible"] is False
    assert "GREEN" not in json.dumps(saved)


def test_smoke_rejects_contract_instead_of_silently_ignoring_it(tmp_path):
    result = invoke("smoke", EXAMPLE, "--root", tmp_path / "runs")
    assert result.returncode == 2
    assert not (tmp_path / "runs").exists()


def test_run_agent_requires_explicit_run_id_before_dispatch(tmp_path):
    result = invoke("run-agent", "m1_minimal_loop", "--root", tmp_path / "runs")
    assert result.returncode == 2
    assert "requires a host-supplied" in result.stderr
    assert not (tmp_path / "runs").exists()


def test_run_id_is_not_silently_ignored_by_other_commands(tmp_path):
    result = invoke("smoke", "--run-id", "a" * 32, "--root", tmp_path / "runs")
    assert result.returncode == 2
    assert not (tmp_path / "runs").exists()
