#!/usr/bin/env python3
# m2_perf_showcase.py — Large-project slicing, export and synchronized video
# feishu: none

import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from threading import Event, Thread
from uuid import uuid4
from zipfile import ZipFile

import cv2
import numpy as np

from m2_slice_chain import (
    HERE, anchors, click_slice_start, launcher, profile, wait_model_loaded,
    wait_slicing_done, winutil,
)
from m2_perf_scenarios import _activate_window, _measure_export, run_soak, run_viewport
from m3f_multi_plate import switch_to_slice_all
from harness import export_util, host_guard, perf_monitor
from harness.showcase_mesh import build_dense_plate

FPS = 8
SAMPLE_SIZE = (1152, 648)


class DesktopRecording:
    def __init__(self, directory):
        self.path = directory / f"{uuid4().hex}.pending.mp4"
        self.timestamps = []
        self.stop = Event()
        self.error = None

    def __enter__(self):
        self.started = time.monotonic()
        self.thread = Thread(target=self._capture, name="showcase-recording", daemon=True)
        self.thread.start()
        return self

    def _capture(self):
        writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SAMPLE_SIZE)
        try:
            if not writer.isOpened():
                raise RuntimeError("MP4 encoder unavailable")
            while not self.stop.is_set():
                timestamp = time.monotonic()
                w, h, pixels = winutil.screen_grab()
                desktop = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)
                small = cv2.resize(desktop, SAMPLE_SIZE, interpolation=cv2.INTER_AREA)
                writer.write(cv2.cvtColor(small, cv2.COLOR_BGRA2BGR))
                self.timestamps.append(round(timestamp - self.started, 5))
                self.stop.wait(max(0, 1 / FPS - (time.monotonic() - timestamp)))
        except (OSError, RuntimeError, ValueError, cv2.error) as error:
            self.error = f"{type(error).__name__}: {error}"
        finally:
            writer.release()

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=8)
        if self.thread.is_alive():
            self.error = "desktop_recorder_did_not_stop"

    def publish(self, stem):
        if not self.error and self.timestamps and self.path.stat().st_size > 0:
            self.path.rename(stem.with_suffix(".mp4"))
            stem.with_suffix(".video.json").write_text(json.dumps({
                "format": "desktop_recording", "fps": FPS,
                "size": SAMPLE_SIZE, "frame_offset_seconds": self.timestamps,
            }), encoding="utf-8")
            return True
        print(f"[showcase] recorder failed: {self.error or 'no frames'}")
        return False


def _slice(session, all_plates):
    monitor = session.perf
    monitor.set_step("slice")
    dispatched = time.monotonic()
    started = False
    if all_plates:
        if switch_to_slice_all(session):
            _, button = export_util.find_slice_buttons(session.hwnd)
            if button and "Slice all" in button[0] and winutil.user32.IsWindowEnabled(button[2]):
                x0, y0, x1, y1 = button[1]
                dispatched = time.monotonic()
                winutil.msg_click_screen((x0 + x1) // 2, (y0 + y1) // 2, session.hwnd)
                started = True
    else:
        started = click_slice_start(session)
        if started:
            dispatched, _ = session.slice_dispatch
    done = started and wait_slicing_done(session, timeout_s=420)[0]
    monitor.measure("slice_click_to_completion_detected", dispatched,
                    status="observed" if done else "not_observed", all_plates=all_plates)
    return done


def _preview(session):
    monitor = session.perf
    monitor.set_step("preview")
    started = time.monotonic()

    def on_dispatch(_attempt, timestamp):
        nonlocal started
        started = timestamp

    already_active = anchors.is_tab_teal(anchors.capture_bgr(session), *anchors.TAB_PREVIEW_PROBE)
    active = already_active or anchors.click_and_verify(
        session, "tab_preview_inactive", "tab_preview_active", attempts=2, on_dispatch=on_dispatch,
    )[0]
    fraction = anchors.has_colored_content(anchors.capture_bgr(session))
    confirmed = active and fraction >= anchors.TOOLPATH_COLORED_FLOOR
    monitor.measure("preview_already_active" if already_active else "preview_click_to_toolpath_detected",
                    started, status="observed" if confirmed else "not_observed", colored_fraction=fraction)
    return confirmed


def _verify_export(session, path):
    started = time.monotonic()
    layer_changes = 0
    with path.open("rb") as stream:
        for line in stream:
            if line.strip() in (b"; CHANGE_LAYER", b";LAYER_CHANGE", b"; LAYER_CHANGE"):
                layer_changes += 1
    verified = layer_changes > 1
    session.perf.measure("showcase_export_layer_evidence", started,
                         status="observed" if verified else "not_observed", layer_changes=layer_changes)
    return verified


def _run(label, model, directory, faces, objects, plates):
    os.environ["ORCA_BB_PERF_LABEL"] = label
    datadir = directory / f"profile-{label}"
    profile.seed_profile(datadir, fresh=True)
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    dims = {}
    with DesktopRecording(directory) as video:
        session = launcher.launch(datadir=datadir, model=model)
        monitor = session.perf
        try:
            if monitor is None:
                raise RuntimeError("showcase requires process performance sampling")
            stem = directory / f"{label}__{monitor.instance_id}"
            monitor.measure("showcase_recording_alignment", video.started, end=video.started)
            time.sleep(12)  # leave the CLI loader and launcher blocker sweep undisturbed
            with _activate_window(session) as active:
                if not active:
                    raise RuntimeError("Orca could not become foreground for video")
                visible, fraction = wait_model_loaded(session, timeout_s=6)
                monitor.measure("launch_to_model_visible", session.launch_started,
                                status="observed" if visible else "not_observed",
                                colored_fraction=fraction, faces=faces, objects=objects,
                                plates=plates, fixture=model.name, sha256=digest)
                dims["slice"] = _slice(session, all_plates=plates > 1)
                dims["preview"] = dims["slice"] and _preview(session)
                if dims["preview"]:
                    if os.environ.get("ORCA_BB_PERF_VIEWPORT") == "1":
                        monitor.set_step("viewport")
                        started = time.monotonic()
                        try:
                            run_viewport(session)
                        except (OSError, RuntimeError, ValueError, cv2.error) as error:
                            monitor.measure("frame_capture", started, status="unavailable", reason=str(error))
                    if os.environ.get("ORCA_BB_PERF_CYCLES", "0") != "0":
                        started = time.monotonic()
                        try:
                            run_soak(session, int(os.environ["ORCA_BB_PERF_CYCLES"]))
                        except (OSError, RuntimeError, ValueError, cv2.error) as error:
                            monitor.measure("soak_cycle", started, status="unavailable", reason=str(error))
                    monitor.set_step("export")
                    dims["gcode"] = _measure_export(session, verify=lambda path: _verify_export(session, path))
                    time.sleep(.6)
        finally:
            session.close()
            dims["close"] = session.popen.returncode == 0
            time.sleep(.4)
    dims["video"] = video.publish(stem)
    return dims


def main():
    host_guard.assert_guest_or_allow()
    output = os.environ.get("ORCA_BB_PERF_BATCH_DIR")
    if not output or not perf_monitor.env_enabled():
        raise RuntimeError("use hv_go -Cases m2_perf_showcase -Perf")
    directory = Path(output)
    winutil.make_dpi_aware()
    fixtures = HERE / "fixtures"
    success = True
    with TemporaryDirectory(prefix="showcase-model-", dir=directory) as work:
        dense = Path(work) / "Ribbed Towers - six objects.3mf"
        count = build_dense_plate(fixtures / "agent_layer_cube.3mf", dense)
        plates = fixtures / "snapmates_nonmixed.3mf"
        with ZipFile(plates) as archive:
            faces = sum(archive.read(path).count(b"<triangle ") for path in archive.namelist()
                        if path.endswith(".model"))
        for label, model, metadata in (("showcase_dense", dense, (count, 6, 1)),
                                       ("showcase_snapmates", plates, (faces, 19, 7))):
            try:
                result = _run(label, model, directory, *metadata)
                for name, passed in result.items():
                    print(f"  {label} {name}: {'PASS' if passed else 'FAIL'}", flush=True)
                success &= all(result.get(name, False) for name in ("slice", "preview", "gcode", "close", "video"))
            except (OSError, RuntimeError, ValueError, cv2.error) as error:
                print(f"  {label}: FAIL ({error})", flush=True)
                success = False
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
