"""Navigate owned wx process groups through their actual viewport."""
import ctypes
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


def _direction(proof):
    viewport_top = proof["bounds"][1]
    group_top = proof["group_bounds"][1]
    return -1 if group_top < viewport_top + 2 else 1 if group_top > viewport_top + 115 else 0


def scroll_group(initial, current, from_handle, check_revocation):
    from win32gui import SendMessageTimeout

    anchor = (initial["hwnd"], initial["bounds"], initial["group_hwnd"])

    def refresh():
        live = current()
        if live is None or (live["hwnd"], live["bounds"], live["group_hwnd"]) != anchor:
            raise ValueError("native_process_viewport_changed")
        check_revocation()
        return live

    viewport, group = map(from_handle, (initial["hwnd"], initial["group_hwnd"]))
    scroll = viewport.GetScrollPattern() if viewport is not None else None
    item = group.GetScrollItemPattern() if group is not None else None
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
            SendMessageTimeout(live["hwnd"], 0x0115, int(direction > 0), 0, 2, 500)
            updated = refresh()
            if updated["group_bounds"] == live["group_bounds"]:
                break
            live = updated
    receipt = {"backend": backends[-1] if backends else "none", "attempted": backends,
               "patterns": patterns, "before": initial, "after": live,
               "scroll_before": before, "scroll_after": _vertical_scroll(initial["hwnd"])}
    return receipt, not _direction(live)
