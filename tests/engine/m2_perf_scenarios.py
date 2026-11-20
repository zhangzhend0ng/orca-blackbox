"""Opt-in m2 viewport and repeated-operation diagnostics on the same Orca PID."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import cv2
import numpy as np

from harness import anchors, perf_frames, winutil


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
    user = winutil.user32
    ex_style = user.GetWindowLongW(session.hwnd, -20)
    user.SetWindowLongW(session.hwnd, -20, ex_style & ~0x08000000)
    if not winutil.move_to_primary_and_foreground(session.hwnd):
        monitor.measure("frame_capture", tools_ready_at, status="unavailable", reason="foreground_unavailable")
        return

    actions = {
        "zoom": lambda direction: _zoom(session, direction),
        "orbit": lambda direction: _drag(session, direction, pan=False),
        "pan": lambda direction: _drag(session, direction, pan=True),
        "preview_layer_scrub": lambda direction: _scrub(session, direction),
    }
    supported = {}
    try:
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
            if capture.process is not None:
                time.sleep(0.8)
                for name, action in supported.items():
                    start, hz = perf_frames.clock()
                    limit = time.monotonic() + 3
                    count = 0
                    while time.monotonic() < limit:
                        action(1 if count % 2 else -1)
                        count += 1
                        time.sleep(0.065)
                    end, _ = perf_frames.clock()
                    spans[name] = (start, end, hz, count)
        if capture.reason:
            monitor.measure("frame_capture", frame_start, status="unavailable", reason=capture.reason)
            return
        frames = perf_frames.read_frames(csv_path, session.pid)
        for name, (start, end, hz, count) in spans.items():
            summary = perf_frames.frame_metrics(frames, start, end)
            monitor.measure("frame_capture", frame_start, status=summary["status"], activity=name,
                            qpc_start=start, qpc_end=end, qpc_hz=hz, inputs=count,
                            csv=csv_path.name, frame_summary=summary)
    finally:
        if session.alive():
            user.SetWindowLongW(session.hwnd, -20, ex_style)


def _close_project(session, m7):
    sent, _ = m7.file_menu_dispatch(session, "New Project")
    if not sent:
        return False
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if not session.alive():
            return False
        if winutil.user32.IsWindowEnabled(session.hwnd):
            if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR:
                return True
        else:
            dlg = m7.wait_dialog(session.pid, timeout_s=.4, title_substr="Snapmaker Orca - Save")
            if dlg:
                labels = [label.strip().replace("&", "").casefold() for label, _ in m7.dialog_buttons(dlg[3])]
                for label in ("don't save", "discard", "no"):
                    if label in labels:
                        m7.click_dialog_button(dlg[3], label, fallback_first=False)
                        break
                else:
                    return False
        time.sleep(0.2)
    return False


def _idle_checkpoint(session, cycle):
    session.perf.set_step("soak_idle")
    # Exclude the first second after closing the project from the idle window.
    time.sleep(1)
    start = time.monotonic()
    time.sleep(2.5)
    session.perf.measure("soak_idle", start, cycle=cycle)


def _measure_export(session):
    from harness import export_util
    with TemporaryDirectory(prefix="perf-export-", dir=session.perf.frame_csv_path.parent) as directory:
        target = Path(directory) / "sample.gcode"
        start = time.monotonic()
        exported = export_util.export_gcode(session, target, timeout_s=25)
        # The existing export helper confirms creation. Keep a separate
        # measurement for stable size/mtime, with a documented sampling bound.
        previous = None
        stable_at = None
        deadline = time.monotonic() + 3
        while exported and time.monotonic() < deadline:
            stat = target.stat()
            current = (stat.st_size, stat.st_mtime_ns)
            if current == previous:
                stable_at = time.monotonic()
                break
            previous = current
            time.sleep(0.25)
        session.perf.measure("export_request_to_stable_file", start, end=stable_at,
                             status="observed" if stable_at else "not_observed",
                             stable_window_ms=250, bytes=previous[0] if stable_at else None)


def run_soak(session, cycles):
    import m7_common as m7
    from m7t83 import import_stl

    monitor = session.perf
    begin = time.monotonic()
    if not _close_project(session, m7):
        monitor.measure("soak_cycle", begin, status="not_observed", cycle=0, reason="empty_bed_not_observed")
        return
    _idle_checkpoint(session, 0)
    for cycle in range(1, cycles + 1):
        session.perf_soak_cycle = cycle
        monitor.set_step("soak_work")
        start = time.monotonic()
        results = {}
        imported = import_stl(session) and m7.step_model_arrives(session, results, timeout_s=60, min_frac=.0025)
        sliced = imported and m7.op_slice(session, results)
        cleared = sliced and _close_project(session, m7)
        monitor.measure("soak_cycle", start, status="observed" if cleared else "not_observed",
                        cycle=cycle, imported=bool(imported), sliced=bool(sliced), cleared=bool(cleared))
        if not cleared:
            return
        _idle_checkpoint(session, cycle)


def run_diagnostics(session):
    if os.environ.get("ORCA_BB_PERF_VIEWPORT") == "1":
        started = time.monotonic()
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
            try:
                _measure_export(session)
            except (OSError, RuntimeError, ValueError) as error:
                session.perf.measure("export_request_to_stable_file", started, status="unavailable",
                                     reason=type(error).__name__)
            run_soak(session, cycles)
        except (OSError, RuntimeError, ValueError) as error:
            session.perf.measure("soak_cycle", started, status="unavailable", reason=type(error).__name__)
