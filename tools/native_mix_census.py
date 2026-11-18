"""Read Add Mix properties with the same UIA runtime used by Windows-MCP."""
import json
from pathlib import Path
import subprocess
import sys


def observer(ui, mode):
    from harness.mix_dialog_util import mixing_util

    def capture(stage, dialog, popup_rect=None):
        ui.guard()
        if not ui.owned_dialog(dialog) or ui.wu.window_title(dialog) != "Add Mix":
            raise ValueError("mix_census_dialog_identity")
        target = dialog
        if popup_rect is not None:
            matches = [hwnd for kind, name, rect, hwnd in mixing_util.toplevel(ui.app.pid)
                       if kind == "wxWindowNR" and name == "panel" and tuple(rect) == tuple(popup_rect) and ui.owned(hwnd)]
            if len(matches) != 1:
                raise ValueError("mix_census_choices_identity")
            target = matches[0]
        image = ui.artifacts / f"mix_controls_{mode.lower()}_{stage}.png"
        process = subprocess.run([r"C:\coil\tools\windows-mcp-0.8.9\python.exe", "-B", __file__,
                                  str(ui.app.hwnd), str(dialog), str(target), str(image)],
                                  check=True, capture_output=True, timeout=30, encoding="utf-8")
        row = json.loads(process.stdout)
        with (ui.artifacts / "mix_controls.ndjson").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(row, mode=mode, stage=stage), ensure_ascii=True) + "\n")
    return capture


def scan(main, dialog, target, image):
    import win32gui as win
    import win32process
    from PIL import ImageGrab
    from windows_mcp.uia import ControlFromHandle

    pid = win32process.GetWindowThreadProcessId(main)[1]
    if any(win32process.GetWindowThreadProcessId(hwnd)[1] != pid or not win.IsWindowVisible(hwnd)
           for hwnd in (dialog, target)) or win.GetAncestor(dialog, 3) != main:
        raise ValueError("mix_census_window_owner")
    bounds = win.GetWindowRect(target)
    with ImageGrab.grab(bbox=bounds) as capture:
        capture.save(image)
    rows = []
    pending = [(ControlFromHandle(target), 0)]
    methods = ("Invoke", "SelectionItem", "Value", "Toggle", "RangeValue", "ExpandCollapse", "LegacyIAccessible")
    while pending and len(rows) < 180:
        item, depth = pending.pop()
        if item.ProcessId != pid:
            continue
        patterns = []
        for method in methods:
            query = getattr(item, "Get" + method + "Pattern", None)
            if query is not None and query() is not None:
                patterns.append(method)
        rect = item.BoundingRectangle
        rows.append(dict(name=item.Name, automation_id=item.AutomationId, type=item.ControlTypeName,
                         hwnd=item.NativeWindowHandle, enabled=item.IsEnabled, offscreen=item.IsOffscreen,
                         rect=[rect.left, rect.top, rect.right, rect.bottom], patterns=patterns))
        if depth < 6:
            pending.extend((child, depth + 1) for child in reversed(item.GetChildren()))
    report = dict(main=main, dialog=dialog, target=target, owner=win.GetWindow(target, 4),
                  root_owner=win.GetAncestor(target, 3), foreground=win.GetForegroundWindow(),
                  kind=win.GetClassName(target), name=win.GetWindowText(target), bounds=bounds, controls=rows)
    if target != dialog:
        if report["owner"] != dialog or report["foreground"] != target:
            raise ValueError("mix_census_popup_not_active")
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                   str(Path(__file__).with_name("native_mix_accessibility.ps1")), str(target), *map(str, bounds)]
        probe = subprocess.run(command, capture_output=True, timeout=20, encoding="utf-8")
        if probe.returncode:
            report["accessibility_probe_error"] = probe.stderr.strip()[-2000:]
        else:
            report["accessibility_probe"] = json.loads(probe.stdout)
    print(json.dumps(report))


if __name__ == "__main__":
    scan(*map(int, sys.argv[1:4]), Path(sys.argv[4]))
