"""Optional recording of the interactive guest desktop, with no UI input."""
import hashlib
import threading
import time


class DesktopVideo:
    fps = 5
    size = (1280, 720)

    def __init__(self, root, capture=None, *, fps=None, size=None):
        self.path = root / "desktop.mp4"
        self.capture = capture
        self.fps = self.fps if fps is None else fps
        self.size = self.size if size is None else size
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.frames = 0
        self.started_at_ns = None
        self.thread = threading.Thread(target=self._record, name="native-desktop-recording", daemon=True)

    def start(self):
        self.thread.start()
        if not self.ready.wait(12) or self.error:
            self.stop.set()
            raise RuntimeError("native_desktop_recorder_start")

    def _record(self):
        writer = None
        temporary = self.path.with_name("desktop.partial.mp4")
        try:
            import cv2
            import numpy as np
            from PIL import ImageGrab

            writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, self.size)
            if not writer.isOpened():
                raise RuntimeError("native_desktop_encoder_open")
            start = time.monotonic()
            self.started_at_ns = time.time_ns()
            previous = None
            while not self.stop.is_set():
                if self.capture is None:
                    with ImageGrab.grab() as image:
                        frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
                else:
                    frame = self.capture()
                frame = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
                target = int((time.monotonic() - start) * self.fps)
                while previous is not None and self.frames < target:
                    writer.write(previous)
                    self.frames += 1
                writer.write(frame)
                self.frames += 1
                previous = frame
                self.ready.set()
                self.stop.wait(max(0, start + self.frames / self.fps - time.monotonic()))
        except Exception as exc:
            self.error = type(exc).__name__
            self.ready.set()
        finally:
            if writer is not None:
                writer.release()
            if self.error is None and self.frames:
                temporary.rename(self.path)

    def finish(self):
        self.stop.set()
        self.thread.join(12)
        if self.thread.is_alive() or self.error or not self.path.is_file():
            raise RuntimeError("native_desktop_recorder_incomplete")
        with self.path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"started_at_ns": self.started_at_ns, "fps": self.fps, "frames": self.frames,
                "width": self.size[0], "height": self.size[1],
                "sha256": digest}
