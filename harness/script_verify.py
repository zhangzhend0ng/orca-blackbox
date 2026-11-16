"""Independent m0 bootstrap verifier, restricted to run-owned guest artifacts.

Valid, non-uniform captures prove only coarse capture/bootstrap behavior, not GL
correctness or slicing. The trusted Job adapter owns process.json and script.log;
the script's report alone is not proof of success or process termination.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import threading

from .run_verdict import CheckResult
from .runtime_ports import CleanupOutcome, Done, Pending, VerificationOutcome

_PHASES = ["launched", "preflight", "captures_complete", "close_requested", "closed"]
_REPORT_KEYS = {"schema_version", "case_id", "driver_pid", "app_pid", "hwnd",
                "phases", "captures", "grab", "keep"}
_PROCESS_KEYS = {"schema_version", "run_id", "case_id", "backend", "pid", "started_at_ns",
                 "finished_at_ns", "exit_code", "active_processes", "job_assigned", "forced_termination", "cancel_reason"}


class _InvalidEvidence(ValueError):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidEvidence("duplicate_json_field")
        result[key] = value
    return result


def _check_cancel(cancelled):
    if cancelled():
        raise _InvalidEvidence("verification_cancelled")


def _read(root, name, start_ns, max_size, cancelled):
    # name is fixed by the verifier (or matched against startup_0..2.bmp),
    # never an arbitrary path supplied by the script.
    _check_cancel(cancelled)
    candidate = root
    for part in name.split("/"):
        candidate = candidate / part
        info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise _InvalidEvidence("artifact_link_rejected")
    with candidate.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 1 <= before.st_size <= max_size or before.st_mtime_ns < start_ns
                or (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)):
            raise _InvalidEvidence("artifact_identity_size_or_freshness")
        chunks = []
        remaining = before.st_size
        while remaining:
            _check_cancel(cancelled)
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                raise _InvalidEvidence("artifact_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise _InvalidEvidence("artifact_grew_during_read")
        after = os.fstat(stream.fileno())
    final = candidate.lstat()
    if (before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
            or (before.st_dev, before.st_ino) != (final.st_dev, final.st_ino)
            or stat.S_ISLNK(final.st_mode) or getattr(final, "st_file_attributes", 0) & 0x400):
        raise _InvalidEvidence("artifact_changed_during_read")
    return b"".join(chunks)


def _json(raw):
    def reject(_value):
        raise _InvalidEvidence("nonfinite_json")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=reject)


def _bmp(raw: bytes, width: int, height: int, cancelled):
    """Validate exactly the uncompressed 32-bit BMP produced by winutil."""
    if len(raw) < 54 or raw[:2] != b"BM":
        raise _InvalidEvidence("capture_bmp_magic")
    size, reserved, offset = struct.unpack_from("<III", raw, 2)
    dib, w, h, planes, bits, compression, image_size = struct.unpack_from("<IiiHHII", raw, 14)
    if (reserved != 0 or offset != 54 or dib != 40 or w != width or h != height
            or not 1 <= w <= 8192 or not 1 <= h <= 8192 or w * h > 16_000_000
            or planes != 1 or bits != 32 or compression != 0
            or image_size != w * h * 4 or size != 54 + image_size or len(raw) != size):
        raise _InvalidEvidence("capture_bmp_structure")
    pixels = memoryview(raw)[54:]
    minima, maxima = [255] * 3, [0] * 3
    for offset in range(0, len(pixels), 65536):
        _check_cancel(cancelled)
        chunk = pixels[offset:offset + 65536]
        for channel in range(3):
            minima[channel] = min(minima[channel], min(chunk[channel::4]))
            maxima[channel] = max(maxima[channel], max(chunk[channel::4]))
        if any(a != b for a, b in zip(minima, maxima)):
            break
    if minima == maxima:
        raise _InvalidEvidence("capture_uniform_pixels")


def verify_m0(snapshot, *, cancelled=lambda: False) -> VerificationOutcome:
    """Check the fixed m0 bootstrap intent; never derive a verdict from rc/GREEN."""
    root = Path(snapshot.artifact_dir)
    start_ns = snapshot.manifest["started_at_ns"]
    evidence = []
    read = lambda name, limit: _read(root, name, start_ns, limit, cancelled)
    try:
        if (snapshot.contract.case_id != "m0_boot_check" or snapshot.contract.executor != "script"
                or tuple(step.id for step in snapshot.contract.steps) != ("boot", "capture", "close")):
            raise _InvalidEvidence("unsupported_case")
        process = _json(read("process.json", 65536))
        if type(process) is not dict or set(process) != _PROCESS_KEYS:
            raise _InvalidEvidence("process_schema")
        if (type(process["schema_version"]) is not int or process["schema_version"] != 1
                or process["run_id"] != snapshot.run_id or process["case_id"] != "m0_boot_check"
                or process["backend"] != "win32_job" or process["job_assigned"] is not True
                or process["forced_termination"] is not False
                or process["cancel_reason"] is not None
                or type(process["pid"]) is not int or process["pid"] <= 0
                or type(process["exit_code"]) is not int or process["exit_code"] != 0
                or type(process["active_processes"]) is not int or process["active_processes"] != 0
                or type(process["started_at_ns"]) is not int
                or type(process["finished_at_ns"]) is not int
                or not start_ns <= process["started_at_ns"] <= process["finished_at_ns"]):
            raise _InvalidEvidence("process_ownership_or_quiescence")
        report = _json(read("m0/report.json", 65536))
        if type(report) is not dict or set(report) != _REPORT_KEYS:
            raise _InvalidEvidence("report_schema")
        if (type(report["schema_version"]) is not int or report["schema_version"] != 1
                or report["case_id"] != "m0_boot_check" or report["phases"] != _PHASES
                or report["grab"] is not False or report["keep"] is not False
                or type(report["driver_pid"]) is not int or report["driver_pid"] != process["pid"]
                or type(report["app_pid"]) is not int or report["app_pid"] <= 0
                or report["app_pid"] == report["driver_pid"]
                or type(report["hwnd"]) is not int or report["hwnd"] <= 0):
            raise _InvalidEvidence("report_bootstrap_phases")
        captures = report["captures"]
        if type(captures) is not list or len(captures) != 3:
            raise _InvalidEvidence("report_capture_count")
        log = read("script.log", 1024 * 1024).decode("utf-8", errors="strict")
        expected_launch = (f"[m0-evidence] launched driver_pid={report['driver_pid']} "
                           f"app_pid={report['app_pid']} hwnd={report['hwnd']}")
        if log.count(expected_launch) != 1 or log.count("[m0] app closed") != 1:
            raise _InvalidEvidence("log_bootstrap_phases")
        launch_index = log.index(expected_launch)
        close_index = log.index("[m0] app closed")
        logged = re.findall(r"\[m0\] capture (\d+): (\d+)x(\d+) -> (startup_\d+\.bmp)", log)
        if len(logged) != 3 or launch_index >= close_index:
            raise _InvalidEvidence("log_capture_count")
        for i, capture in enumerate(captures):
            if (type(capture) is not dict or set(capture) != {"filename", "width", "height"}
                    or capture["filename"] != f"startup_{i}.bmp"
                    or type(capture["width"]) is not int or type(capture["height"]) is not int):
                raise _InvalidEvidence("report_capture_schema")
            expected_log = (str(i), str(capture["width"]), str(capture["height"]), capture["filename"])
            if logged[i] != expected_log:
                raise _InvalidEvidence("log_report_capture_mismatch")
            marker = f"[m0] capture {i}: {capture['width']}x{capture['height']} -> {capture['filename']}"
            index = log.index(marker)
            if not launch_index < index < close_index:
                raise _InvalidEvidence("log_capture_order")
            name = "m0/" + capture["filename"]
            raw = read(name, 64 * 1024 * 1024)
            _bmp(raw, capture["width"], capture["height"], cancelled)
            evidence.append("artifact:" + name + ":sha256:" + hashlib.sha256(raw).hexdigest())
        refs = tuple(evidence + ["artifact:m0/report.json", "artifact:script.log", "artifact:process.json"])
        checks = {name: CheckResult("pass", "m0 bootstrap/capture/owned process exit only", refs)
                  for name in ("path", "business")}
        return VerificationOutcome(checks, True, True)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        detail = str(exc) if isinstance(exc, _InvalidEvidence) else "bootstrap_evidence_unavailable"
        checks = {name: CheckResult("unknown", detail) for name in ("path", "business")}
        return VerificationOutcome(checks, False, False)


class _VerifierCleanup:
    def __init__(self, operation):
        self.operation = operation

    def poll(self):
        if self.operation._worker.is_alive():
            return Pending()
        return Done(CleanupOutcome(True))


class _ReadOnlyHandle:
    def __init__(self, snapshot):
        self._done = threading.Event()
        self._cancelled = threading.Event()
        self._result = None
        self._error = None
        def work():
            try:
                self._result = verify_m0(snapshot, cancelled=self._cancelled.is_set)
            except BaseException as exc:
                self._error = exc
            finally:
                self._done.set()
        # A stuck read-only OS operation must not keep the CLI interpreter alive
        # after runtime has quarantined the lease. This does not confirm cleanup.
        self._worker = threading.Thread(target=work, name="m0-evidence-verifier", daemon=True)
        self._worker.start()

    def poll(self):
        if not self._done.is_set() or self._worker.is_alive():
            return Pending()
        if self._error is not None:
            raise self._error
        if self._cancelled.is_set():
            return Done(VerificationOutcome({}, False, False))
        return Done(self._result)

    def cancel(self, reason):
        # Python reads cannot be forcibly interrupted. Cleanup remains pending
        # until the read-only worker is actually quiescent; runtime may isolate.
        self._cancelled.set()

    def start_cleanup(self):
        return _VerifierCleanup(self)


class M0ScriptVerifier:
    """Trusted read-only guest verifier; runtime must keep results script_shadow."""
    synthetic = False

    def start(self, snapshot):
        return _ReadOnlyHandle(snapshot)
