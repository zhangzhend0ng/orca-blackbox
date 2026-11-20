"""Navigate owned wx process groups through their actual viewport."""
import ctypes
import hashlib
from io import BytesIO
import subprocess
from ctypes import wintypes
import time

PROCESS_GROUPS = ("Seam", "Ironing")
PROCESS_VALUES = {"Aligned", "Random", "No ironing", "Topmost surface"}


def _inside(inner, outer):
    return (outer[0] <= inner[0] < inner[2] <= outer[2]
            and outer[1] <= inner[1] < inner[3] <= outer[3])


def _children(hwnd):
    from win32gui import EnumChildWindows

    children = []
    EnumChildWindows(hwnd, lambda child, rows: rows.append(child) or True, children)
    return children


def _vertical_scroll(hwnd):
    from win32gui import GetWindowLong

    if not GetWindowLong(hwnd, -16) & 0x00200000:  # WS_VSCROLL
        return None
    info = ScrollInfo(ctypes.sizeof(ScrollInfo), 0x0007)  # SIF_RANGE | SIF_PAGE | SIF_POS
    if not ctypes.windll.user32.GetScrollInfo(wintypes.HWND(hwnd), 1, ctypes.byref(info)):
        return None
    return [info.minimum, info.maximum, info.page, info.position]


class ScrollInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.UINT), ("mask", wintypes.UINT), ("minimum", ctypes.c_int),
        ("maximum", ctypes.c_int), ("page", wintypes.UINT), ("position", ctypes.c_int),
        ("track_position", ctypes.c_int),
    ]


def process_viewports(wu, main, pid, sidebar):
    from win32gui import GetParent, IsWindowVisible

    if sidebar is None:
        return {}, {}
    groups, values = {}, {}
    duplicates, duplicate_values = set(), set()
    for child in _children(main):
        if (wu._window_pid(child) != pid or wu.window_class(child) != "wxWindowNR"
                or not IsWindowVisible(child)):
            continue
        title = wu.window_title(child)
        if title not in PROCESS_GROUPS and title not in PROCESS_VALUES:
            continue
        bounds = list(wu.window_rect(child))
        parent = GetParent(child)
        while parent and parent != main and wu._window_pid(parent) == pid:
            viewport = list(wu.window_rect(parent))
            if (wu.window_class(parent) == "wxWindowNR" and wu.window_title(parent) == "panel"
                    and _inside(viewport, sidebar) and _vertical_scroll(parent) is not None):
                break
            parent = GetParent(parent)
        else:
            continue
        if title in PROCESS_VALUES:
            if _inside(bounds, viewport):
                if title in values:
                    duplicate_values.add(title)
                values[title] = bounds
            continue
        if bounds[2] - bounds[0] < 100:
            continue
        if title in groups:
            duplicates.add(title)
        groups[title] = {"group": title, "hwnd": parent, "bounds": viewport,
                         "group_hwnd": child, "group_bounds": bounds}
    return ({name: item for name, item in groups.items() if name not in duplicates},
            {value: values[value] for value in sorted(values) if value not in duplicate_values})


def recheck_viewport(wu, main, pid, sidebar, observed):
    from win32gui import IsChild, IsWindowVisible

    viewport, child = observed["hwnd"], observed["group_hwnd"]
    if (sidebar is None or not IsChild(main, viewport) or not IsChild(viewport, child)
            or any(wu._window_pid(item) != pid or wu.window_class(item) != "wxWindowNR"
                   or not IsWindowVisible(item) for item in (viewport, child))
            or wu.window_title(viewport) != "panel" or wu.window_title(child) != observed["group"]
            or not _inside(observed["bounds"], sidebar) or list(wu.window_rect(viewport)) != observed["bounds"]):
        return None
    return dict(observed, group_bounds=list(wu.window_rect(child)))


def read_ironing_selection(wu, main, pid, group, binding, root):
    """Read the same visible, previously opened custom combo after its rebuild."""
    from win32gui import IsChild

    if group is None or group["hwnd"] != binding["viewport_hwnd"]:
        return None
    left, top = group["group_bounds"][:2]
    bounds = [edge + offset for edge, offset in zip(binding["relative_rect"], (left, top, left, top))]
    if not _inside(bounds, group["bounds"]) or not IsChild(main, group["hwnd"]):
        return None
    target = wu.window_from_screen_point((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
    if (not target or not IsChild(group["hwnd"], target) or wu._window_pid(target) != pid
            or wu.window_class(target) != "wxWindowNR" or list(wu.window_rect(target)) != bounds):
        return None
    buffer = ctypes.create_unicode_buffer(128)
    wu._send_msg(target, 0x000D, len(buffer), ctypes.cast(buffer, ctypes.c_void_p), timeout_ms=500)  # WM_GETTEXT
    proof = {"hwnd": target, "bounds": bounds, "raw": buffer.value}
    if buffer.value.strip().casefold() in {"topmost surface", "topmost surface only"}:
        return dict(proof, backend="WM_GETTEXT")

    from PIL import ImageGrab

    # The wx field paints an ellipsis at this width. In this enum only the
    # topmost option starts with "Topmost sur".
    image = ImageGrab.grab(bbox=(bounds[0] + 18, bounds[1], bounds[2], bounds[3])).convert("L")
    prepared = BytesIO()
    image.resize((image.width * 4, image.height * 4)).save(prepared, format="PNG")
    result = subprocess.run([r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        "stdin", "stdout", "-l", "eng", "--psm", "7"], input=prepared.getvalue(),
        capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    text = result.stdout.decode("utf-8", errors="replace").strip()
    words = text.casefold().rstrip(".…").split()
    if (result.returncode or len(words) != 2 or words[0] != "topmost"
            or len(words[1]) < 3 or not "surface".startswith(words[1])):
        return None
    digest = hashlib.sha256(prepared.getvalue()).hexdigest()
    path = root / f"process_readback_{digest}.png"
    if not path.exists():
        with path.open("xb") as stream:
            stream.write(prepared.getvalue())
    return dict(proof, backend="scoped_ocr", painted_text=text, image=path.name, sha256=digest)


def _direction(proof):
    viewport_top = proof["bounds"][1]
    group_top = proof["group_bounds"][1]
    return -1 if group_top < viewport_top + 2 else 1 if group_top > viewport_top + 115 else 0


def scroll_group(initial, current, from_handle, check_revocation):
    from windows_mcp.uia.controls import PatternId
    from .winutil import _send_msg

    anchor = (initial["hwnd"], initial["bounds"], initial["group_hwnd"])

    def refresh():
        live = current()
        if live is None or (live["hwnd"], live["bounds"], live["group_hwnd"]) != anchor:
            raise ValueError("native_process_viewport_changed")
        check_revocation()
        return live

    viewport, group = map(from_handle, (initial["hwnd"], initial["group_hwnd"]))
    # Generic wx HWNDs map to controls without the specialized pattern helpers.
    # Query actual provider capability through the base Control API.
    scroll = viewport.GetPattern(PatternId.ScrollPattern) if viewport is not None else None
    item = group.GetPattern(PatternId.ScrollItemPattern) if group is not None else None
    patterns = []
    if scroll is not None and scroll.VerticallyScrollable:
        patterns.append("ScrollPattern")
    if item is not None:
        patterns.append("ScrollItemPattern")
    backends = []
    live = refresh()
    before = _vertical_scroll(initial["hwnd"])
    if _direction(live) and item is not None:
        item.ScrollIntoView()
        backends.append("ScrollItemPattern")
        live = refresh()
    if _direction(live) and "ScrollPattern" in patterns:
        backends.append("ScrollPattern")
        for _ in range(32):
            direction = _direction(live)
            if not direction:
                break
            scroll.Scroll(2, 4 if direction > 0 else 1)  # NoAmount, SmallIncrement/Decrement
            updated = refresh()
            if updated["group_bounds"] == live["group_bounds"]:
                break
            live = updated
    if _direction(live):
        backends.append("WM_VSCROLL")
        stopped = time.monotonic() + 8
        for _ in range(220):
            direction = _direction(live)
            if not direction or time.monotonic() >= stopped:
                break
            # The owned viewport handles its standard vertical scrollbar line commands.
            _send_msg(live["hwnd"], 0x0115, int(direction > 0), 0, timeout_ms=500)
            updated = refresh()
            if updated["group_bounds"] == live["group_bounds"]:
                break
            live = updated
    receipt = {"backend": backends[-1] if backends else "none", "attempted": backends,
               "patterns": patterns, "before": initial, "after": live,
               "scroll_before": before, "scroll_after": _vertical_scroll(initial["hwnd"])}
    return receipt, not _direction(live)
