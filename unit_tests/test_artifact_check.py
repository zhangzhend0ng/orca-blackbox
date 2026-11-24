"""Artifact provenance/freshness challenges using temporary files, without GUI."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.artifact_check import check_artifact

START = 1_700_000_000_000_000_000


@pytest.fixture
def artifact(tmp_path):
    p = tmp_path / "out.gcode"
    p.write_bytes(b"; layer_height = 0.4\nG1 X1\n; END\n")
    os.utime(p, ns=(START + 100, START + 100))
    return p


def check(artifact, **kwargs):
    return check_artifact(artifact.parent, artifact.name, started_at_ns=START, **kwargs)


def test_fresh_artifact_evidence_contains_hash(artifact):
    result = check(artifact, expected_config={"layer_height": "0.4"}, required_suffix=b"; END\n")
    assert result.status == "pass"
    assert "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest() in result.evidence
    assert "correctness not established" in result.detail


def test_stale_artifact_is_not_success(artifact):
    os.utime(artifact, ns=(START - 100, START - 100))
    assert check(artifact).detail == "artifact_stale"


def test_empty_artifact_is_not_success(artifact):
    artifact.write_bytes(b"")
    assert check(artifact).status == "fail"


def test_missing_artifact_is_unknown(tmp_path):
    assert check_artifact(tmp_path, "missing.gcode", started_at_ns=START).status == "unknown"


def test_truncation_detected_by_independent_completeness_expectation(artifact):
    original_size = artifact.stat().st_size
    artifact.write_bytes(b"; layer_height = 0.4\n")
    assert check(artifact, expected_size=original_size).detail == "artifact_size_mismatch"
    assert check(artifact, required_suffix=b"; END\n").detail == "artifact_end_marker_missing"


def test_hash_mismatch_and_conflicting_config_echoes_fail(artifact):
    assert check(artifact, expected_sha256="0" * 64).detail == "artifact_hash_mismatch"
    artifact.write_bytes(b"; layer_height = 0.4\n; layer_height = 0.2\n")
    assert check(artifact, expected_config={"layer_height": "0.4"}).status == "fail"


def test_missing_config_and_wrong_value_fail(artifact):
    assert check(artifact, expected_config={"wall_loops": "3"}).status == "fail"
    assert check(artifact, expected_config={"layer_height": "0.2"}).status == "fail"


@pytest.mark.parametrize("path", ["../secret", "a/../../secret", "/etc/passwd",
                                    "C:\\secret", "\\\\server\\secret", "out.gcode:stream",
                                    "a//b", "./out.gcode", "a/../out.gcode",
                                    "a/.. /out.gcode", "out.gcode.", "NUL", "CON.txt",
                                    "a\nfile"])
def test_path_escape_and_aliases_rejected(tmp_path, path):
    assert check_artifact(tmp_path, path, started_at_ns=START).detail == "artifact_path_invalid"


def test_directory_is_not_accepted(tmp_path):
    (tmp_path / "directory").mkdir()
    assert check_artifact(tmp_path, "directory", started_at_ns=START).status != "pass"


def test_symbolic_link_is_rejected(artifact):
    link = artifact.parent / "alias.gcode"
    try:
        link.symlink_to(artifact)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc.winerror if hasattr(exc, 'winerror') else exc.errno}")
    assert check_artifact(artifact.parent, link.name, started_at_ns=START).detail == "artifact_link_rejected"


def test_windows_reparse_flag_is_rejected_without_following(artifact, monkeypatch):
    original = Path.lstat
    def flagged(path):
        info = original(path)
        if path == artifact:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, "lstat", flagged)
    assert check(artifact).detail == "artifact_link_rejected"


def test_hardlink_is_rejected(artifact):
    alias = artifact.parent / "hardlink.gcode"
    os.link(artifact, alias)
    assert check(artifact).detail == "artifact_hardlink_rejected"


def test_file_identity_change_before_read_is_unknown(artifact, monkeypatch):
    from harness import artifact_check
    original = os.fstat
    def replaced(fd):
        info = original(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_dev=info.st_dev,
                               st_ino=info.st_ino + 1)
    monkeypatch.setattr(artifact_check, "os", SimpleNamespace(fstat=replaced))
    assert check(artifact).detail == "artifact_replaced_before_read"


@pytest.mark.parametrize("kwargs", [{"started_at_ns": True}, {"max_size": float("nan")},
                                     {"expected_size": True}, {"min_size": 0},
                                     {"expected_sha256": "bad"}, {"required_suffix": b""},
                                     {"expected_config": {"bad\nkey": "x"}}])
def test_invalid_checker_configuration_rejected(artifact, kwargs):
    args = {"started_at_ns": START, **kwargs}
    with pytest.raises(ValueError):
        check_artifact(artifact.parent, artifact.name, **args)
