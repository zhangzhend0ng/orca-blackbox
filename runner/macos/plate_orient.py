"""Choose the plate's Auto Rotate row in the isolated Aqua login."""
import subprocess
import time

import accessibility as ax


def right_click(desktop, pid, root, window, title, x, depth):
    wid, origin = desktop.slice_window(pid, root, window, title)
    if not ax.post_allowed():
        raise RuntimeError("Targeted input requires event posting permission")
    make_mouse = ax.selector(b"mouseEventWithType:location:modifierFlags:timestamp:"
                             b"windowNumber:context:eventNumber:clickCount:pressure:")
    for kind in (3, 4):  # AppKit rightMouseDown / rightMouseUp.
        desktop.check_owned(pid, window)
        event = ax.mouse_event(ax.objc_class(b"NSEvent"), make_mouse, kind,
                               ax.Point(x, 800 - depth), 0, time.monotonic(),
                               wid, None, 1, 1, float(kind == 3))
        if not event or ax.event_window(event, ax.selector(b"windowNumber")) != wid:
            raise RuntimeError("Right-click event lost its project window")
        native = ax.event_cg(event, ax.selector(b"CGEvent"))
        if not native:
            raise RuntimeError("Right-click event is unavailable")
        ax.set_location(native, ax.Point(origin.x + x, origin.y + depth))
        ax.post_to_pid(pid, native)
        time.sleep(.16)


def popup_items(desktop, root, window):
    focused = desktop.attr(root, "AXFocusedUIElement")
    parent = desktop.attr(focused, "AXParent") if focused else None
    candidates = {*desktop.children(root), *desktop.children(window), focused, parent}
    menus = [node for node in candidates if node and desktop.text(node, "AXRole") == "AXMenu"]
    return [[(desktop.text(row, "AXTitle"), row) for row in desktop.children(menu)
             if desktop.text(row, "AXRole") == "AXMenuItem"] for menu in menus]


def choose_auto_rotate(desktop, pid, root, window, title, report):
    attempts = []
    report["context_menu_attempts"] = attempts
    for x, depth in ((800, 550), (865, 575)):
        right_click(desktop, pid, root, window, title, x, depth)
        time.sleep(.8)
        popups = popup_items(desktop, root, window)
        attempts.append({"window_point": [x, depth], "menus": [[title for title, _ in popup] for popup in popups]})
        print(f"Auto Rotate plate menu attempt {attempts[-1]}", flush=True)
        hits = []
        for popup in popups:
            names = {name for name, _ in popup}
            if {"Select All", "Delete All", "Arrange", "Auto Rotate"} <= names:
                hits.extend(row for name, row in popup if name == "Auto Rotate" and desktop.enabled(row))
        if len(hits) == 1:
            desktop.act(pid, hits[0], "AXPress")
            report["menu_item"] = "Auto Rotate"
            return
        desktop.post_key(pid, root, window, title, 53, 1)  # Dismiss failed popup with Escape.
    raise RuntimeError("Blank-plate context menu did not expose a unique enabled Auto Rotate item")


def capture_project(desktop, pid, root, window, title, target):
    wid, _ = desktop.slice_window(pid, root, window, title)
    try:
        subprocess.run(["/usr/sbin/screencapture", "-x", "-o", "-l", str(wid), str(target)],
                       capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass
    for path in (target, target.with_name("." + target.name)):
        if path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
            blob = path.read_bytes()
            if blob.startswith(b"\x89PNG\r\n\x1a\n") and blob.endswith(b"IEND\xaeB\x60\x82"):
                if path != target:
                    path.replace(target)
                return True
    return False
