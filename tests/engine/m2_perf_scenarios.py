"""Opt-in m2 viewport and repeated-operation diagnostics on the same Orca PID."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import cv2
import numpy as np

from harness import anchors, perf_frames, winutil


@contextmanager
def _activate_window(session):
    user = winutil.user32
    ex_style = user.GetWindowLongW(session.hwnd, -20)
    user.SetWindowLongW(session.hwnd, -20, ex_style & ~0x08000000)
    try:
        yield winutil.move_to_primary_and_foreground(session.hwnd)
    finally:
        if session.alive():
            user.SetWindowLongW(session.hwnd, -20, ex_style)


def _surface(session):
    image = anchors.viewport_crop(anchors.capture_bgr(session))
    h, w = image.shape[:2]
    # Sample the central viewport and exclude controls around the edges.
    center = image[h // 5:4 * h // 5, w // 6:5 * w // 6]
    return cv2.resize(center, (128, 96), interpolation=cv2.INTER_AREA)


def _canvas(session, x, y):
    if (not session.alive() or winutil.user32.GetForegroundWindow() != session.hwnd):
        raise RuntimeError("orcas_window_not_foreground")
    target = winutil.window_from_screen_point(x, y)
    if not target or winutil._window_pid(target) != session.pid:
        raise RuntimeError("viewport_hit_outside_orca")
    if target != session.hwnd and not winutil.user32.IsChild(session.hwnd, target):
        raise RuntimeError("viewport_hit_outside_main_window")
    return target


def _point(session):
    left, top, right, bottom = session.rect()
    return (left + anchors.VIEWPORT_X0 + (right - left - anchors.VIEWPORT_X0) // 3,
            top + (bottom - top) // 2)


def _zoom(session, direction):
    x, y = _point(session)
    _canvas(session, x, y)
    winutil.user32.SetCursorPos(x, y)
    winutil.user32.mouse_event(winutil.MOUSEEVENTF_WHEEL, 0, 0, 120 * direction, 0)


def _drag(session, direction, *, pan):
    x, y = _point(session)
    down, up = (0x20, 0x40) if pan else (winutil.MOUSEEVENTF_LEFTDOWN, winutil.MOUSEEVENTF_LEFTUP)
    # An empty patch of the view lets the left drag orbit the camera.
    x -= 48
    y -= 95
    _canvas(session, x, y)
    winutil.user32.SetCursorPos(x, y)
    winutil.user32.mouse_event(down, 0, 0, 0, 0)
    try:
        for offset in range(5, 81, 5):
            _canvas(session, x + offset * direction, y + offset // 4)
            winutil.user32.SetCursorPos(x + offset * direction, y + offset // 4)
            time.sleep(0.018)
    finally:
        winutil.user32.mouse_event(up, 0, 0, 0, 0)


def _scrub(session, direction):
    x, y = _point(session)
    target = _canvas(session, x, y)
    # Preview's canvas handles Up/Down as layer changes.
    if target == session.hwnd or "canvas" not in winutil.window_class(target).lower():
        raise RuntimeError("preview_canvas_not_observed")
    winutil.msg_key(target, 0x26 if direction > 0 else 0x28)


def _visually_changed(before, after):
    diff = cv2.absdiff(before, after)
    return float(np.count_nonzero(np.max(diff, axis=2) >= 18)) / (diff.shape[0] * diff.shape[1]) >= .025


def _observe_response(session, name, action):
    before = _surface(session)
    start = time.monotonic()
    action(-1)
    deadline = start + 2
    last_negative = start
    while True:
        sample_start = time.monotonic()
        changed = _visually_changed(before, _surface(session))
        observed = time.monotonic()
        if changed or observed >= deadline:
            break
        last_negative = sample_start
        time.sleep(0.035)
    session.perf.measure(name + "_input_to_viewport_change", start, end=observed,
                         status="observed" if changed else "not_observed",
                         observation_lower_ms=(last_negative - start) * 1000 if changed else None,
                         observer="viewport_pixels")
    return changed


def run_viewport(session):
    monitor = session.perf
    tools_ready_at = time.monotonic()
    # This happens after functional Preview validation and outside the
    # read-only startup window. Make only the owned Orca window activatable.
    actions = {
        "zoom": lambda direction: _zoom(session, direction),
        "orbit": lambda direction: _drag(session, direction, pan=False),
        "pan": lambda direction: _drag(session, direction, pan=True),
        "preview_layer_scrub": lambda direction: _scrub(session, direction),
    }
    supported = {}
    with _activate_window(session) as active:
        if not active:
            monitor.measure("frame_capture", tools_ready_at, status="unavailable", reason="foreground_unavailable")
            return
        for name, action in actions.items():
            start = time.monotonic()
            try:
                if _observe_response(session, name, action):
                    supported[name] = action
                    action(1)
            except (OSError, RuntimeError, ValueError) as error:
                monitor.measure(name + "_input_to_viewport_change", start, status="unavailable",
                                reason=str(error))
        if not supported:
            monitor.measure("frame_capture", tools_ready_at, status="unavailable", reason="no_verified_activity")
            return

        csv_path = monitor.frame_csv_path
        spans = {}
        frame_start = time.monotonic()
        with perf_frames.FrameCapture(session.pid, csv_path, monitor.instance_id, 17) as capture:
            tracing = session.render_trace_path is not None
            if capture.process is not None or tracing:
                if capture.process is not None:
                    time.sleep(0.8)
                for name, action in supported.items():
                    if not tracing and capture.process.poll() is not None:
                        break
                    start, hz = perf_frames.clock()
                    began = time.monotonic()
                    limit = began + 3
                    count = 0
                    while time.monotonic() < limit:
                        try:
                            action(1 if count % 2 else -1)
                        except (OSError, RuntimeError, ValueError) as error:
                            monitor.measure("frame_activity_interrupted", frame_start,
                                            status="not_observed", activity=name, reason=str(error))
                            break
                        count += 1
                        time.sleep(0.065)
                    end, _ = perf_frames.clock()
                    if count:
                        spans[name] = (start, end, hz, count)
                    if tracing:
                        monitor.measure("render_activity", began, status="observed" if count else "not_observed",
                                        activity=name, qpc_start=start, qpc_end=end, qpc_hz=hz, inputs=count)
        reason, frames = capture.reason, []
        if not reason:
            try:
                frames = perf_frames.read_frames(csv_path, session.pid)
            except (OSError, ValueError) as error:
                reason = str(error)
        if not spans:
            monitor.measure("frame_capture", frame_start, status="unavailable",
                            reason=reason or "no_activity_window", collector_error=capture.error)
        for name, (start, end, hz, count) in spans.items():
            summary = perf_frames.frame_metrics(frames, start, end) if not reason else None
            monitor.measure("frame_capture", frame_start,
                            status=summary["status"] if summary else "unavailable",
                            reason=reason, activity=name, collector_error=capture.error,
                            qpc_start=start, qpc_end=end, qpc_hz=hz, inputs=count,
                            csv=csv_path.name, frame_summary=summary)


def _idle_checkpoint(session, cycle):
    session.perf.set_step("soak_idle")
    # Exclude the first second after the UI action from the idle window.
    time.sleep(1)
    start = time.monotonic()
    time.sleep(2.5)
    session.perf.measure("soak_idle", start, cycle=cycle)


def _measure_export(session, *, verify=None):
    from harness import export_util
    import m7_common as m7

    with TemporaryDirectory(prefix="perf-export-", dir=session.perf.frame_csv_path.parent) as directory:
        target = Path(directory) / "sample.gcode"
        start = time.monotonic()
        sent, _ = m7.file_menu_dispatch(session, "Export G-code", via="Export")
        dialog = m7.wait_dialog(session.pid, timeout_s=8, title_substr="Save G-code file as") if sent else None
        session.perf.measure("export_request_to_save_dialog", start,
                             status="observed" if dialog else "not_observed")
        edit = export_util.find_edit(dialog[3]) if dialog else None
        if not edit or winutil._window_pid(edit) != session.pid:
            session.perf.measure("export_request_to_stable_file", start, status="not_observed",
                                 reason="save_filename_edit_unavailable")
            return False
        winutil.select_all(edit)
        winutil.msg_text(edit, str(target))
        confirm_at = time.monotonic()
        winutil._send_msg(dialog[3], 0x0111, 1, 0)  # WM_COMMAND IDOK on the owned Save dialog
        previous = None
        first_seen = None
        stable_at = None
        deadline = confirm_at + 25
        while time.monotonic() < deadline and session.alive():
            try:
                stat = target.stat()
            except (FileNotFoundError, PermissionError):
                time.sleep(.1)
                continue
            current = (stat.st_size, stat.st_mtime_ns)
            now = time.monotonic()
            if current != previous:
                previous, first_seen = current, now
            elif current[0] > 0 and now - first_seen >= .25:
                stable_at = now
                break
            time.sleep(.1)
        for name, began in (("export_request_to_stable_file", start),
                            ("export_confirm_to_stable_file", confirm_at)):
            session.perf.measure(name, began, end=stable_at,
                                 status="observed" if stable_at else "not_observed",
                                 stable_window_ms=250, bytes=previous[0] if stable_at else None)
        if stable_at and verify is not None:
            return verify(target)
        return bool(stable_at)


def run_soak(session, cycles):
    monitor = session.perf
    _idle_checkpoint(session, 0)
    for cycle in range(1, cycles + 1):
        monitor.set_step("soak_work")
        start = time.monotonic()
        prepare, _ = anchors.click_and_verify(session, "tab_prepare_inactive", "tab_prepare_active", attempts=2)
        preview_at = time.monotonic()
        monitor.measure("soak_prepare_transition", start, end=preview_at, cycle=cycle,
                        status="observed" if prepare else "not_observed")
        preview = False
        if prepare:
            active, _ = anchors.click_and_verify(session, "tab_preview_inactive", "tab_preview_active", attempts=2)
            preview = active and (anchors.has_colored_content(anchors.capture_bgr(session))
                                  >= anchors.TOOLPATH_COLORED_FLOOR)
        monitor.measure("soak_preview_transition", preview_at, cycle=cycle,
                        status="observed" if preview else "not_observed" if prepare else "skipped")
        monitor.measure("soak_cycle", start, status="observed" if preview else "not_observed",
                        cycle=cycle, prepare=prepare, preview_toolpath=preview)
        if not preview:
            return
        _idle_checkpoint(session, cycle)


def run_diagnostics(session):
    if os.environ.get("ORCA_BB_PERF_VIEWPORT") == "1":
        started = time.monotonic()
        session.perf.set_step("viewport")
        try:
            run_viewport(session)
        except (OSError, RuntimeError, ValueError) as error:
            session.perf.measure("frame_capture", started, status="unavailable", reason=type(error).__name__)
    try:
        cycles = int(os.environ.get("ORCA_BB_PERF_CYCLES", "0"))
    except ValueError:
        cycles = 0
    if cycles:
        started = time.monotonic()
        try:
            session.perf.frame_csv_path.parent.mkdir(parents=True, exist_ok=True)
            run_soak(session, cycles)
        except (OSError, RuntimeError, ValueError) as error:
            session.perf.measure("soak_cycle", started, status="unavailable", reason=type(error).__name__)
        started = time.monotonic()
        try:
            session.perf.set_step("export")
            _measure_export(session)
        except (OSError, RuntimeError, ValueError) as error:
            session.perf.measure("export_request_to_stable_file", started, status="unavailable",
                                 reason=type(error).__name__)
