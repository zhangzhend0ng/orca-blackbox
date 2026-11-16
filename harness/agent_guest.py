"""Guest-only fixed tab observation/click worker. No model, shell or arbitrary tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import zlib

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness import host_guard
from harness.agent_protocol import (MAX_CALLS, MAX_CLICKS, MAX_RUNTIME_S, LAYER_CASE, ProtocolError, agent_profile,
                                    check_cancel, read_json, valid_run_id, validate_request, write_json_once)
from harness.run_contract import load_contract
from harness.run_verdict import contract_digest


def _bytes_once(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _encode_capture(capture):
    width, height, pixels = capture
    if (type(width) is not int or type(height) is not int or not 313 <= width <= 4096
            or not 68 <= height <= 2160 or len(pixels) != width * height * 4):
        raise ProtocolError("invalid_capture")
    bmp = (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
           + struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(pixels), 2835, 2835, 0, 0)
           + pixels)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rgb = bytearray()
    for start in range(0, len(pixels), width * 4):
        rgb.append(0)
        row = pixels[start:start + width * 4]
        for offset in range(0, len(row), 4):
            rgb.extend((row[offset + 2], row[offset + 1], row[offset]))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rgb)) + chunk(b"IEND", b""))
    return bmp, png


class _WindowsUI:
    def __init__(self, artifacts, model=None):
        from harness import launcher, profile, winutil
        self.winutil = winutil
        target = artifacts / "profile"
        if target.exists():
            raise FileExistsError("profile already exists")
        profile.seed_profile(target, fresh=False)
        self.app = launcher.launch(datadir=target, model=model, dismiss_wizard=True)
        self.shape = None

    def identity(self):
        app, wu = self.app, self.winutil
        if not app.alive() or not wu.user32.IsWindow(app.hwnd) or wu._window_pid(app.hwnd) != app.pid:
            raise ProtocolError("window_identity_changed")
        capture = wu.capture_window(app.hwnd)
        width, height = capture[:2]
        dpi = wu.get_dpi_for_window(app.hwnd)
        if dpi != 96 or (self.shape is not None and self.shape != (width, height)):
            raise ProtocolError("window_geometry_changed")
        self.shape = (width, height)
        return {"hwnd": app.hwnd, "pid": app.pid, "width": width, "height": height, "dpi": dpi}, capture

    def click(self, x, y):
        self.identity()
        self.winutil.msg_click_client(self.app.hwnd, x, y, root_hwnd=self.app.hwnd)

    def close(self):
        if self.app.alive():
            if self.winutil._window_pid(self.app.hwnd) != self.app.pid:
                raise ProtocolError("window_identity_changed")
            self.winutil.close_window(self.app.hwnd)
            deadline = time.monotonic() + 10
            while self.app.alive() and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.app.alive():
                raise ProtocolError("graceful_close_unconfirmed")


def run_guest(artifact_dir: Path, run_id: str, digest: str) -> int:
    if not host_guard.in_guest():
        raise PermissionError("agent worker requires Hyper-V guest")
    valid_run_id(run_id)
    artifacts = artifact_dir.resolve(strict=True)
    contract = load_contract(artifacts.parent / "contract.json")
    if (contract.contract_version != agent_profile(contract.case_id)["contract_version"]
            or contract.executor != "agent_mcp" or contract_digest(contract) != digest):
        raise ProtocolError("wrong_contract")
    for path in (artifacts / "mailbox", artifacts / "frames", artifacts / "ready.json",
                 artifacts / "agent_report.json", artifacts / "trace.ndjson",
                 artifacts / "operation_receipts.ndjson"):
        if path.exists():
            raise FileExistsError("agent artifacts must start empty")
    mailbox, frames = artifacts / "mailbox", artifacts / "frames"
    mailbox.mkdir()
    frames.mkdir()
    started_ns, deadline = time.time_ns(), time.monotonic() + MAX_RUNTIME_S
    calls, clicks, last_observation, status, ui = 0, 0, None, "failed", None
    driver_pid, app_pid, hwnd = os.getpid(), None, None
    def guard():
        check_cancel(artifacts, run_id)
        if time.monotonic() >= deadline:
            raise ProtocolError("worker_deadline")
    def receipt(seq, method, request, start_ns, details):
        raw = None if request is None else json.dumps(request, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        row = {"schema_version": 1, "run_id": run_id, "seq": seq, "method": method,
            "request_sha256": None if raw is None else hashlib.sha256(raw).hexdigest(),
            "started_at_ns": start_ns, "finished_at_ns": time.time_ns(),
            "window": {"hwnd": hwnd, "pid": app_pid}, "details": details}
        with (artifacts / "operation_receipts.ndjson").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    operations = {"edit": 0, "slice": 0, "export_gcode": 0}
    with (artifacts / "trace.ndjson").open("x", encoding="utf-8") as trace:
        try:
            check_cancel(artifacts, run_id)
            if contract.case_id == LAYER_CASE:
                from harness.agent_business_ui import BusinessUI
                _bytes_once(artifacts / "operation_receipts.ndjson", b"")
                ui = BusinessUI(artifacts, guard)
            else:
                ui = _WindowsUI(artifacts)
            window, _capture = ui.identity()
            app_pid, hwnd = window["pid"], window["hwnd"]
            if contract.case_id == LAYER_CASE:
                receipt(0, "boot", None, started_ns, ui.boot_details)
            write_json_once(artifacts / "ready.json", {"schema_version": 1, "run_id": run_id,
                "case_id": contract.case_id, "driver_pid": driver_pid, "app_pid": app_pid,
                "hwnd": hwnd, "contract_sha256": digest})
            for seq in range(1, MAX_CALLS + 1):
                check_cancel(artifacts, run_id)
                request_path = mailbox / f"request_{seq:04d}.json"
                while not request_path.exists():
                    check_cancel(artifacts, run_id)
                    if time.monotonic() >= deadline:
                        raise ProtocolError("worker_deadline")
                    time.sleep(0.05)
                request = None
                response = {"schema_version": 1, "run_id": run_id, "seq": seq,
                            "tool": "observe", "is_error": False, "error_code": None,
                            "observation": None, "finished": False}
                try:
                    request = validate_request(read_json(request_path), run_id=run_id,
                                               expected_seq=seq, observation_id=last_observation,
                                               case_id=contract.case_id)
                    calls += 1
                    method = request["method"]
                    response["tool"] = method
                    if method == "click":
                        check_cancel(artifacts, run_id)
                        if clicks >= MAX_CLICKS:
                            raise ProtocolError("click_budget")
                        clicks += 1
                        ui.click(**request["arguments"])
                    elif method in operations:
                        guard()
                        if operations[method] >= 2:
                            raise ProtocolError("operation_budget")
                        operations[method] += 1
                        operation_start = time.time_ns()
                        details = ui.perform(method, request["arguments"])
                        guard()
                        receipt(seq, method, request, operation_start, details)
                    captured = []
                    for suffix in ("a", "b"):
                        check_cancel(artifacts, run_id)
                        if time.monotonic() >= deadline:
                            raise ProtocolError("worker_deadline")
                        if suffix == "b":
                            time.sleep(1.05)
                        if time.monotonic() >= deadline:
                            raise ProtocolError("worker_deadline")
                        check_cancel(artifacts, run_id)
                        window, capture = ui.identity()
                        check_cancel(artifacts, run_id)
                        timestamp = time.time_ns()
                        bmp, png = _encode_capture(capture)
                        relative = f"frames/{seq:04d}_{suffix}.bmp"
                        _bytes_once(artifacts / relative, bmp)
                        check_cancel(artifacts, run_id)
                        captured.append({"path": relative, "sha256": hashlib.sha256(bmp).hexdigest(),
                            "width": capture[0], "height": capture[1], "captured_at_ns": timestamp})
                    png_relative = f"frames/{seq:04d}.png"
                    _bytes_once(artifacts / png_relative, png)
                    last_observation = f"{run_id}_{seq:04d}"
                    response["observation"] = {"id": last_observation, "frames": captured,
                        "image": {"path": png_relative, "sha256": hashlib.sha256(png).hexdigest(),
                                  "size_bytes": len(png)}, "window": window}
                    if method == "finish":
                        check_cancel(artifacts, run_id)
                        ui.close()
                        response["finished"] = True
                        status = "completed"
                except Exception as exc:
                    response.update(is_error=True, error_code=str(exc) if isinstance(exc, ProtocolError)
                                    else "tool_error")
                trace.write(json.dumps({"request": request if request is not None else {"invalid": True},
                                        "response": response}, sort_keys=True) + "\n")
                trace.flush()
                os.fsync(trace.fileno())
                write_json_once(mailbox / f"response_{seq:04d}.json", response)
                if response["finished"] or response["is_error"]:
                    break
        except Exception as exc:
            status = "failed"
            print(f"[agent_guest] stopped: {type(exc).__name__}", file=sys.stderr)
        finally:
            if ui is not None:
                try:
                    ui.close()
                except Exception:
                    status = "failed"
            write_json_once(artifacts / "agent_report.json", {"schema_version": 1,
                "run_id": run_id, "case_id": contract.case_id, "driver_pid": driver_pid,
                "app_pid": app_pid, "hwnd": hwnd, "started_at_ns": started_ns,
                "finished_at_ns": time.time_ns(), "status": status, "calls": calls, "clicks": clicks})
    return 0 if status == "completed" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--contract-sha256", required=True)
    args = parser.parse_args()
    return run_guest(args.artifact_dir, args.run_id, args.contract_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
