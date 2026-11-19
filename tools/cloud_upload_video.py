"""Window-only video of a post-login Orca upload-path replay."""
from __future__ import annotations

import threading


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


class LiveDesktopCapture:
    """Full interactive guest recording, with a synchronized sign-in pause."""

    def __init__(self, app, result):
        import cv2
        import numpy as np
        from PIL import ImageGrab

        self.app = app
        self.result = result
        self.cv2 = cv2
        self.np = np
        self.grab = ImageGrab.grab
        with self.grab() as image:
            self.size = image.size
        self.lock = threading.Lock()
        self.hidden = False
        self.privacy_frames = 0
        self.foreground_console_frames = 0
        width, height = self.size
        self.slate = np.full((height, width, 3), (34, 27, 24), dtype=np.uint8)
        cv2.putText(self.slate, "Orca | signing in", (width // 2 - 225, height // 2 - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, (242, 242, 242), 2, cv2.LINE_AA)
        cv2.putText(self.slate, "Credential entry hidden", (width // 2 - 225, height // 2 + 51),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (214, 214, 214), 2, cv2.LINE_AA)

    def hide_sign_in(self):
        with self.lock:
            self.hidden = True

    def show_signed_in(self):
        with self.lock:
            self.hidden = False

    def frame(self):
        from harness import winutil

        with self.lock:
            if self.hidden:
                self.privacy_frames += 1
                return self.slate
            with self.grab() as image:
                frame = self.cv2.cvtColor(self.np.asarray(image), self.cv2.COLOR_RGB2BGR)
            foreground = winutil.user32.GetForegroundWindow()
            if foreground and winutil.window_class(foreground) in {
                "ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS",
            }:
                self.foreground_console_frames += 1
            if (not self.result.get("new_project_requested") and self.result.get("home_signed_in")
                    and self.result.get("device_stage", "") in {
                "", "find_my_devices", "read_my_devices", "device_page_observed", "find_u1_device_control",
                    }):
                # Cover the account card only. Keep the title bar, tabs,
                # navigation, and the device content of the desktop intact.
                x, y = winutil.client_to_screen(self.app.hwnd, 0, 0)
                ratio = winutil.get_dpi_for_window(self.app.hwnd) / 96
                left, top = max(0, x), max(0, y + round(67 * ratio))
                right = min(frame.shape[1], x + round(262 * ratio))
                bottom = min(frame.shape[0], y + round(226 * ratio))
                if right > left and bottom > top:
                    frame[top:bottom, left:right] = (248, 248, 248)
            return frame
