"""Check run-local artifact facts, without claiming complete slicer correctness.

The scheduler must own the run root and start time. Freshness and hashes cannot
authenticate files against a malicious process able to rewrite that root.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from collections.abc import Mapping

from . import gcode_check
from .run_verdict import CheckResult

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def check_artifact(run_dir: Path | str, relative_path: str, *, started_at_ns: int,
                   min_size: int = 1, max_size: int = MAX_ARTIFACT_BYTES,
                   expected_size: int | None = None,
                   expected_sha256: str | None = None,
                   required_suffix: bytes | None = None,
                   expected_config: Mapping[str, str] | None = None) -> CheckResult:
    """Return file-fact check evidence. Optional expectations are trusted inputs.

    min_size alone does not establish completeness. Use an independently known
    size/hash/end marker or a format-specific checker to detect truncation.
    Config echoes prove only the echoed configuration, not toolpath correctness.
    """
    if (type(started_at_ns) is not int or started_at_ns <= 0
            or type(min_size) is not int or type(max_size) is not int
            or not 1 <= min_size <= max_size <= MAX_ARTIFACT_BYTES):
        raise ValueError("invalid artifact time or size bounds")
    if expected_size is not None and (type(expected_size) is not int
                                     or not min_size <= expected_size <= max_size):
        raise ValueError("invalid expected artifact size")
    if expected_sha256 is not None and (not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise ValueError("invalid expected SHA256")
    if required_suffix is not None and (not isinstance(required_suffix, bytes)
                                       or not 1 <= len(required_suffix) <= 4096):
        raise ValueError("invalid required suffix")
    if expected_config is not None and (not isinstance(expected_config, Mapping)
            or not 1 <= len(expected_config) <= 100
            or any(not isinstance(k, str) or re.fullmatch(r"[A-Za-z0-9_]{1,128}", k) is None
                   or not isinstance(v, str) or len(v) > 4096
                   for k, v in expected_config.items())):
        raise ValueError("invalid expected config echoes")
    if (not isinstance(relative_path, str) or not relative_path or len(relative_path) > 1024
            or "\x00" in relative_path or ":" in relative_path
            or PureWindowsPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).drive
            or Path(relative_path).is_absolute()):
        return CheckResult("fail", "artifact_path_invalid")
    parts = relative_path.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") or p.endswith((".", " "))
           or PureWindowsPath(p).is_reserved()
           or any(ord(c) < 32 or c in '<>"|?*' for c in p)
           for p in parts):
        return CheckResult("fail", "artifact_path_invalid")
    try:
        root = Path(run_dir).resolve(strict=True)
        candidate = root
        for part in parts:
            candidate = candidate / part
            info = candidate.lstat()
            # Includes symlinks/junctions on Windows; do not follow reparse points.
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                return CheckResult("fail", "artifact_link_rejected")
        candidate.resolve(strict=True).relative_to(root)
        with candidate.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return CheckResult("fail", "artifact_not_regular")
            if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
                return CheckResult("unknown", "artifact_replaced_before_read")
            if before.st_nlink != 1:
                return CheckResult("fail", "artifact_hardlink_rejected")
            if before.st_mtime_ns < started_at_ns:
                return CheckResult("fail", "artifact_stale")
            if not min_size <= before.st_size <= max_size:
                return CheckResult("fail", "artifact_size_out_of_bounds")
            if expected_size is not None and before.st_size != expected_size:
                return CheckResult("fail", "artifact_size_mismatch")
            data = stream.read(max_size + 1)
            after = os.fstat(stream.fileno())
        if (len(data) != before.st_size or before.st_mtime_ns != after.st_mtime_ns
                or before.st_size != after.st_size):
            return CheckResult("unknown", "artifact_changed_during_read")
        final = candidate.lstat()
        if (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino):
            return CheckResult("unknown", "artifact_replaced_during_read")
        if (stat.S_ISLNK(final.st_mode)
                or getattr(final, "st_file_attributes", 0) & 0x400):
            return CheckResult("fail", "artifact_link_rejected")
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            return CheckResult("fail", "artifact_hash_mismatch")
        if required_suffix is not None and not data.endswith(required_suffix):
            return CheckResult("fail", "artifact_end_marker_missing")
        for key, expected in (expected_config or {}).items():
            values = gcode_check.config_value_all(data, key)
            if not values or any(value != expected for value in values):
                return CheckResult("fail", "artifact_config_echo_mismatch")
        return CheckResult("pass", "artifact facts verified; format/toolpath correctness not established",
                           ("artifact:" + "/".join(parts), "sha256:" + digest))
    except (OSError, ValueError):
        return CheckResult("unknown", "artifact_unavailable_or_invalid_root")
