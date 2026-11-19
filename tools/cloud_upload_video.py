"""Window-only video of a post-login Orca upload-path replay."""
from __future__ import annotations


def capture(app, result):
    import cv2
    import numpy as np

    from harness import winutil

    foreground = winutil.user32.GetForegroundWindow()
    owned = {hwnd for hwnd, pid in winutil.enum_windows() if pid == app.pid}
    hwnd = foreground if foreground in owned else app.hwnd
    width, height, raw = winutil.capture_window(hwnd)
    frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))[:, :, :3].copy()
    if hwnd == app.hwnd and result.get("upload_stage") is None:
        # The signed-in home and device panes can include the account card.
        frame[: min(height, 235), : min(width, 265)] = (32, 32, 32)
    canvas = np.full((720, 1280, 3), 24, dtype=np.uint8)
    scale = min(1280 / width, 665 / height)
    sized = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
    rows, cols = sized.shape[:2]
    x, y = (1280 - cols) // 2, (665 - rows) // 2
    canvas[y:y+rows, x:x+cols] = sized
    cv2.putText(canvas, "Orca on win11-test | U1 upload-path replay | stops before Send",
                (28, 701), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (235, 235, 235), 1, cv2.LINE_AA)
    return canvas
