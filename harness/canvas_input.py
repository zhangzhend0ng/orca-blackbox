"""Read-only window census and pure input authority; never sends GUI input.

Default admission requires PFD evidence. An explicit reviewed diagnostic
profile can bind observed wxGLCanvas identity with PFD still unknown. Neither
mode proves an internal text field is active. Not a security sandbox.
"""
from dataclasses import dataclass
from decimal import Decimal
import re


class CanvasInputRejected(ValueError):
    pass


def _need(condition, reason):
    if not condition:
        raise CanvasInputRejected(reason)


def _positive_int(value):
    return type(value) is int and value > 0


def _rect(value):
    return (type(value) is list and len(value) == 4 and all(type(x) is int for x in value)
            and value[0] < value[2] and value[1] < value[3])


def numeric_text_allowed(scenario, text):
    """Only the transform pilot gains positive three-digit numeric authority."""
    if type(text) is not str or len(text) > 16:
        return False
    if scenario == "pilot_transform":
        return bool(re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,4})?", text)
                    and Decimal(text) > 0)
    return bool(re.fullmatch(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,4})?", text))


@dataclass(frozen=True)
class CanvasBinding:
    run_id: str
    app_pid: int
    process_created: int
    main_hwnd: int
    hwnd: int
    window_class: str
    parent: int
    thread_id: int
    main_rect: tuple
    parent_chain: tuple
    desktop: str
    session_id: int
    diagnostic_id: str
    mode: str = "pfd"
    approval_profile: str | None = None
    approval_version: int | None = None
    diagnostic_sha256: str | None = None
    sut_sha256: str | None = None
    window_title: str | None = None


def _environment(evidence):
    _need(type(evidence) is dict and evidence.get("schema_version") == 1, "canvas_evidence_schema")
    _need(type(evidence.get("run_id")) is str and
          re.fullmatch(r"[0-9a-f]{32}", evidence["run_id"]), "canvas_run_id")
    _need(all(_positive_int(evidence.get(k)) for k in
              ("app_pid", "process_created", "main_hwnd", "captured_monotonic_ns")), "canvas_identity")
    _need(type(evidence.get("session_id")) is int and evidence["session_id"] >= 0
          and type(evidence.get("active_session_id")) is int
          and evidence["session_id"] == evidence["active_session_id"], "canvas_session")
    _need(type(evidence.get("thread_desktop")) is str and bool(evidence["thread_desktop"])
          and evidence["thread_desktop"] == evidence.get("input_desktop"), "canvas_input_desktop")
    _need(evidence.get("screen") == [1920, 1080] and evidence.get("complete") is True,
          "canvas_screen_or_incomplete")
    rows = evidence.get("windows")
    _need(type(rows) is list and 1 <= len(rows) <= 260, "canvas_window_limit")
    windows = {}
    for row in rows:
        _need(type(row) is dict and _positive_int(row.get("hwnd")) and row["hwnd"] not in windows,
              "canvas_duplicate_or_invalid_window")
        windows[row["hwnd"]] = row
    _owned(windows.get(evidence["main_hwnd"]), evidence, allow_disabled=True)
    return windows


def _owned(row, evidence, *, allow_disabled=False):
    _need(type(row) is dict and row.get("pid") == evidence["app_pid"]
          and type(row.get("pid")) is int and row.get("exists") is True
          and row.get("visible") is True
          and (row.get("enabled") is True or (allow_disabled and row.get("enabled") is False)),
          "canvas_window_not_owned_or_ready")
    _need(type(row.get("class")) is str and 1 <= len(row["class"]) <= 256
          and _positive_int(row.get("thread_id")) and _rect(row.get("rect"))
          and _rect(row.get("client_rect")) and type(row.get("dpi")) is int and row["dpi"] == 96,
          "canvas_window_geometry")
    return row


def _canvas_geometry(row, main):
    _need(main["rect"][0] <= row["rect"][0] < row["rect"][2] <= main["rect"][2]
          and main["rect"][1] <= row["rect"][1] < row["rect"][3] <= main["rect"][3],
          "canvas_outside_main")


def _opengl(row):
    pfd = row.get("pixel_format")
    _need(type(pfd) is dict and _positive_int(pfd.get("index"))
          and type(pfd.get("describe_count")) is int and pfd["describe_count"] >= pfd["index"]
          and type(pfd.get("flags")) is int and pfd["flags"] & 0x24 == 0x24,
          "canvas_opengl_unproven")  # PFD_SUPPORT_OPENGL | PFD_DRAW_TO_WINDOW


def _parent_chain(row, windows, evidence):
    chain, seen = [], set()
    current = row
    for _ in range(32):
        _owned(current, evidence)
        hwnd = current.get("hwnd")
        _need(hwnd not in seen and current.get("pid") == evidence["app_pid"]
              and type(current.get("pid")) is int and current.get("exists") is True
              and type(current.get("class")) is str and bool(current["class"])
              and _positive_int(current.get("thread_id")), "canvas_parent_chain")
        seen.add(hwnd)
        chain.append((hwnd, current.get("parent"), current["pid"], current["class"], current["thread_id"]))
        if hwnd == evidence["main_hwnd"]:
            return tuple(chain)
        parent = current.get("parent")
        _need(_positive_int(parent) and parent in windows, "canvas_parent_chain")
        current = windows[parent]
    raise CanvasInputRejected("canvas_parent_chain_limit")


def bind_canvas(evidence, canvas_hwnd, *, approved_class, diagnostic_id, approval=None):
    """Trusted setup only: explicit diagnostic selection, never model arguments."""
    _need(type(approved_class) is str and 1 <= len(approved_class) <= 256
          and approved_class != "Edit", "canvas_class_not_approved")
    _need(type(diagnostic_id) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", diagnostic_id),
          "canvas_diagnostic_required")
    windows = _environment(evidence)
    _need(_positive_int(canvas_hwnd) and canvas_hwnd != evidence["main_hwnd"], "canvas_not_child")
    row = _owned(windows.get(canvas_hwnd), evidence)
    _need(row["class"] == approved_class and row.get("is_main_child") is True
          and _positive_int(row.get("parent")), "canvas_binding_mismatch")
    main = windows[evidence["main_hwnd"]]
    if approval is None:
        _opengl(row)
    else:
        from .canvas_approval import validate_approval
        try:
            validate_approval(approval)
        except ValueError as exc:
            raise CanvasInputRejected("canvas_approval_not_registered") from exc
        _need(row["class"] == approval.window_class and row.get("title") == approval.window_title
              and diagnostic_id == approval.diagnostic_run_id, "canvas_observed_identity")
        candidates = [r for r in windows.values() if r.get("pid") == evidence["app_pid"]
            and r.get("exists") is True and r.get("visible") is True and r.get("is_main_child") is True
            and r.get("class") == approval.window_class and r.get("title") == approval.window_title]
        _need(len(candidates) == 1 and candidates[0]["hwnd"] == canvas_hwnd,
              "canvas_observed_candidate_ambiguous")
    _canvas_geometry(row, main)
    chain = _parent_chain(row, windows, evidence)
    return CanvasBinding(evidence["run_id"], evidence["app_pid"], evidence["process_created"],
        evidence["main_hwnd"], canvas_hwnd, approved_class, row["parent"], row["thread_id"],
        tuple(main["rect"]), chain,
        evidence["thread_desktop"], evidence["session_id"], diagnostic_id,
        "pfd" if approval is None else approval.mode,
        None if approval is None else approval.profile_id,
        None if approval is None else approval.version,
        None if approval is None else approval.diagnostic_sha256,
        None if approval is None else approval.sut_sha256,
        None if approval is None else approval.window_title)


def decide_type(scenario, text, loc, evidence, *, output_path, now_ns, binding=None, revoked=False):
    """Return native_edit/canvas_numeric only after a fresh trusted observation.

    Caller retains original Type options validation, serializes dispatch and
    checks cancellation immediately before input. No returned value types text.
    """
    from .native_matrix import SCENARIOS
    _need(type(scenario) is str and scenario in SCENARIOS, "canvas_scenario_unregistered")
    _need(type(revoked) is bool and not revoked, "canvas_input_revoked")
    _need(type(output_path) is str and bool(output_path) and len(output_path) <= 1024,
          "canvas_output_path")
    _need(type(text) is str and len(text) <= 1024, "canvas_text_type")
    is_path = text == output_path
    _need(is_path or numeric_text_allowed(scenario, text), "canvas_numeric_range")
    windows = _environment(evidence)
    _need(type(now_ns) is int and 0 <= now_ns-evidence["captured_monotonic_ns"] <= 1_000_000_000,
          "canvas_evidence_stale")
    _need(type(loc) is list and len(loc) == 2 and all(type(x) is int for x in loc)
          and 0 <= loc[0] < 1920 and 0 <= loc[1] < 1080 and evidence.get("loc") == loc,
          "canvas_location")
    foreground = _owned(windows.get(evidence.get("foreground_hwnd")), evidence)
    target = _owned(windows.get(evidence.get("target_hwnd")), evidence)
    focus = _owned(windows.get(evidence.get("focus_hwnd")), evidence)
    _need(target["rect"][0] <= loc[0] < target["rect"][2]
          and target["rect"][1] <= loc[1] < target["rect"][3], "canvas_target_rect")
    if target["class"] == "Edit":
        # Native Edit retains the existing owned-window route. Focus need not
        # already be the Edit because original Type itself selects its loc.
        if is_path:
            _need(foreground.get("title") in {"Save file as", "Save file as:"}
                  and foreground.get("class") == "#32770"
                  and target.get("root_hwnd") == foreground["hwnd"], "canvas_path_requires_save_edit")
        return {"route": "native_edit", "target_hwnd": target["hwnd"]}
    _need(not is_path and scenario == "pilot_transform" and type(binding) is CanvasBinding,
          "canvas_binding_required")
    _need((binding.run_id, binding.app_pid, binding.process_created, binding.main_hwnd,
           binding.desktop, binding.session_id) ==
          (evidence["run_id"], evidence["app_pid"], evidence["process_created"], evidence["main_hwnd"],
           evidence["thread_desktop"], evidence["session_id"]), "canvas_run_binding_changed")
    _need(target["hwnd"] == focus["hwnd"] == binding.hwnd
          and foreground["hwnd"] == binding.main_hwnd, "canvas_focus_or_foreground_changed")
    if binding.mode == "pfd":
        _need(all(getattr(binding, key) is None for key in
                  ("approval_profile", "approval_version", "diagnostic_sha256", "sut_sha256", "window_title")),
              "canvas_pfd_binding_metadata")
        _opengl(target)
    else:
        approval = _binding_approval(binding)
        _need(target["class"] == approval.window_class and target.get("title") == approval.window_title,
              "canvas_observed_identity")
    _canvas_geometry(target, windows[binding.main_hwnd])
    _need(target.get("is_main_child") is True and
          (target["class"], target.get("parent"), target["thread_id"],
           _parent_chain(target, windows, evidence), tuple(windows[binding.main_hwnd]["rect"])) ==
          (binding.window_class, binding.parent, binding.thread_id,
           binding.parent_chain, binding.main_rect), "canvas_window_binding_changed")
    return {"route": "canvas_numeric", "target_hwnd": target["hwnd"],
            "diagnostic_id": binding.diagnostic_id, "approval_mode": binding.mode}


def _binding_approval(binding):
    from .canvas_approval import resolve_approval
    _need(binding.mode == "observed_wxglcanvas", "canvas_approval_mode")
    try:
        approval = resolve_approval(binding.approval_profile, diagnostic_sha256=binding.diagnostic_sha256,
                                    sut_sha256=binding.sut_sha256)
    except ValueError as exc:
        raise CanvasInputRejected("canvas_approval_provenance") from exc
    _need(type(binding.approval_version) is int and binding.approval_version == approval.version
          and binding.window_class == approval.window_class and binding.window_title == approval.window_title
          and binding.diagnostic_id == approval.diagnostic_run_id, "canvas_approval_metadata")
    return approval


def binding_to_json(binding):
    from dataclasses import asdict
    import json
    _need(type(binding) is CanvasBinding, "canvas_binding_type")
    return json.dumps(asdict(binding), separators=(",", ":"), allow_nan=False)


def load_canvas_binding(raw, *, run_id, app_pid, process_created, main_hwnd, approval=None):
    """Load only trusted run-owned storage, with independent expected scope.

    This is strict validation, not authentication or a writable model tool.
    An observed-mode record additionally needs independently resolved approval.
    """
    import json
    _need(type(raw) in (bytes, str) and 1 <= len(raw) <= 16384, "canvas_binding_json_size")
    if type(raw) is str:
        try:
            _need(len(raw.encode("utf-8")) <= 16384, "canvas_binding_json_size")
        except UnicodeError as exc:
            raise CanvasInputRejected("canvas_binding_json_invalid") from exc
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "canvas_binding_duplicate_key")
            result[key] = value
        return result
    def constant(_):
        raise CanvasInputRejected("canvas_binding_json_constant")
    try:
        data = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CanvasInputRejected("canvas_binding_json_invalid") from exc
    _need(type(data) is dict and set(data) == set(CanvasBinding.__dataclass_fields__),
          "canvas_binding_fields")
    _need(type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id)
          and all(_positive_int(x) for x in (app_pid, process_created, main_hwnd)), "canvas_binding_scope")
    _need(type(data["run_id"]) is str and
          all(_positive_int(data[k]) for k in ("app_pid", "process_created", "main_hwnd", "hwnd", "parent", "thread_id"))
          and (data["run_id"], data["app_pid"], data["process_created"], data["main_hwnd"]) ==
          (run_id, app_pid, process_created, main_hwnd), "canvas_binding_scope")
    _need(data["hwnd"] != main_hwnd and type(data["window_class"]) is str
          and 1 <= len(data["window_class"]) <= 256 and data["window_class"] != "Edit"
          and type(data["desktop"]) is str and 1 <= len(data["desktop"]) <= 256
          and type(data["session_id"]) is int and data["session_id"] >= 0
          and type(data["diagnostic_id"]) is str
          and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", data["diagnostic_id"]), "canvas_binding_values")
    _need(_rect(data["main_rect"]) and all(-2**31 <= v < 2**31 for v in data["main_rect"]),
          "canvas_binding_rect")
    chain = data["parent_chain"]
    _need(type(chain) is list and 2 <= len(chain) <= 32, "canvas_binding_chain")
    seen = set()
    for i, row in enumerate(chain):
        _need(type(row) is list and len(row) == 5 and _positive_int(row[0])
              and type(row[1]) is int and row[1] >= 0 and type(row[2]) is int and row[2] == app_pid
              and type(row[3]) is str and 1 <= len(row[3]) <= 256 and _positive_int(row[4])
              and row[0] not in seen, "canvas_binding_chain")
        seen.add(row[0])
        if i < len(chain)-1:
            _need(type(chain[i+1]) is list and len(chain[i+1]) == 5 and row[1] == chain[i+1][0],
                  "canvas_binding_chain")
    _need(chain[0] == [data["hwnd"], data["parent"], app_pid, data["window_class"], data["thread_id"]]
          and chain[-1][0] == main_hwnd, "canvas_binding_chain")
    data["main_rect"] = tuple(data["main_rect"])
    data["parent_chain"] = tuple(tuple(row) for row in chain)
    binding = CanvasBinding(**data)
    if binding.mode == "pfd":
        _need(approval is None and all(getattr(binding, key) is None for key in
                  ("approval_profile", "approval_version", "diagnostic_sha256", "sut_sha256", "window_title")),
              "canvas_pfd_binding_metadata")
    else:
        observed = _binding_approval(binding)
        from .canvas_approval import validate_approval
        try:
            _need(validate_approval(approval) == observed, "canvas_binding_approval_required")
        except ValueError as exc:
            raise CanvasInputRejected("canvas_binding_approval_required") from exc
    return binding


def collect_window_evidence(run_id, app_pid, main_hwnd, loc=None):
    """Windows INTERACTIVE read-only census; no focus, input, launch or file I/O.

    Enumerates actual classes, never labels a window as a canvas. API failures
    raise rather than returning a guessed/partially authorized identity.
    """
    import ctypes as C
    from ctypes import wintypes as W
    import time
    from . import host_guard
    _need(host_guard.in_guest(), "canvas_diagnostic_guest_only")
    _need(type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id), "canvas_run_id")
    _need(_positive_int(app_pid) and _positive_int(main_hwnd), "canvas_identity")
    _need(loc is None or (type(loc) is list and len(loc) == 2 and all(type(v) is int for v in loc)
                         and 0 <= loc[0] < 1920 and 0 <= loc[1] < 1080), "canvas_location")
    observation_started = time.monotonic_ns()
    u, k = C.WinDLL("user32", use_last_error=True), C.WinDLL("kernel32", use_last_error=True)
    g = C.WinDLL("gdi32", use_last_error=True)
    def api(lib, name, restype, *args):
        function = getattr(lib, name)
        function.restype, function.argtypes = restype, list(args)
        return function
    api(u, "GetWindowThreadProcessId", W.DWORD, W.HWND, C.POINTER(W.DWORD))
    for name in ("GetParent", "GetForegroundWindow"):
        api(u, name, W.HWND, *([W.HWND] if name == "GetParent" else []))
    api(u, "GetAncestor", W.HWND, W.HWND, W.UINT)
    api(u, "WindowFromPoint", W.HWND, W.POINT)
    for name in ("GetWindowRect", "GetClientRect"):
        api(u, name, W.BOOL, W.HWND, C.POINTER(W.RECT))
    for name in ("IsWindow", "IsWindowVisible", "IsWindowEnabled"):
        api(u, name, W.BOOL, W.HWND)
    api(u, "IsChild", W.BOOL, W.HWND, W.HWND)
    api(u, "GetDpiForWindow", W.UINT, W.HWND)
    for name in ("GetClassNameW", "GetWindowTextW"):
        api(u, name, C.c_int, W.HWND, W.LPWSTR, C.c_int)
    api(k, "ProcessIdToSessionId", W.BOOL, W.DWORD, C.POINTER(W.DWORD))
    api(k, "WTSGetActiveConsoleSessionId", W.DWORD)
    api(k, "GetCurrentThreadId", W.DWORD)
    api(k, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
    api(k, "CloseHandle", W.BOOL, W.HANDLE)
    api(k, "GetProcessTimes", W.BOOL, W.HANDLE, *([C.POINTER(W.FILETIME)] * 4))
    api(u, "GetThreadDesktop", W.HANDLE, W.DWORD)
    api(u, "OpenInputDesktop", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
    api(u, "CloseDesktop", W.BOOL, W.HANDLE)
    api(u, "GetUserObjectInformationW", W.BOOL, W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD))
    api(u, "GetDC", W.HDC, W.HWND)
    api(u, "ReleaseDC", C.c_int, W.HWND, W.HDC)
    api(g, "GetPixelFormat", C.c_int, W.HDC)
    class PIXELFORMATDESCRIPTOR(C.Structure):
        _fields_ = [("nSize", W.WORD), ("nVersion", W.WORD), ("dwFlags", W.DWORD)] + [
            (name, W.BYTE) for name in ("iPixelType", "cColorBits", "cRedBits", "cRedShift",
                "cGreenBits", "cGreenShift", "cBlueBits", "cBlueShift", "cAlphaBits", "cAlphaShift",
                "cAccumBits", "cAccumRedBits", "cAccumGreenBits", "cAccumBlueBits", "cAccumAlphaBits",
                "cDepthBits", "cStencilBits", "cAuxBuffers", "iLayerType", "bReserved")] + [
            (name, W.DWORD) for name in ("dwLayerMask", "dwVisibleMask", "dwDamageMask")]
    api(g, "DescribePixelFormat", C.c_int, W.HDC, C.c_int, W.UINT, C.POINTER(PIXELFORMATDESCRIPTOR))
    def pixel_format(hwnd):
        dc = u.GetDC(hwnd)
        if not dc:
            return {"index": 0, "describe_count": 0, "flags": 0, "query_error": "GetDC"}
        try:
            index = g.GetPixelFormat(dc)
            pfd = PIXELFORMATDESCRIPTOR(nSize=C.sizeof(PIXELFORMATDESCRIPTOR), nVersion=1)
            count = g.DescribePixelFormat(dc, index, C.sizeof(pfd), C.byref(pfd)) if index else 0
            return {"index": index, "describe_count": count, "flags": int(pfd.dwFlags),
                    "descriptor": {name: int(getattr(pfd, name)) for name, _ in pfd._fields_}}
        finally:
            _need(u.ReleaseDC(hwnd, dc) == 1, "canvas_release_dc_failed")

    class GUITHREADINFO(C.Structure):
        _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD)] + [
            (name, W.HWND) for name in ("hwndActive", "hwndFocus", "hwndCapture", "hwndMenuOwner",
                                       "hwndMoveSize", "hwndCaret")] + [("rcCaret", W.RECT)]
    api(u, "GetGUIThreadInfo", W.BOOL, W.DWORD, C.POINTER(GUITHREADINFO))
    pid = W.DWORD()
    thread = u.GetWindowThreadProcessId(main_hwnd, C.byref(pid))
    _need(pid.value == app_pid and thread, "canvas_main_identity")
    process = k.OpenProcess(0x1000, False, app_pid)  # QUERY_LIMITED_INFORMATION
    _need(bool(process), "canvas_process_query")
    try:
        times = [W.FILETIME() for _ in range(4)]
        _need(k.GetProcessTimes(process, *(C.byref(t) for t in times)), "canvas_process_times")
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        k.CloseHandle(process)
    session = W.DWORD()
    _need(k.ProcessIdToSessionId(app_pid, C.byref(session)), "canvas_session_query")
    def desktop_name(handle):
        name, needed = C.create_unicode_buffer(256), W.DWORD()
        _need(handle and u.GetUserObjectInformationW(handle, 2, name, C.sizeof(name), C.byref(needed)),
              "canvas_desktop_query")
        return name.value
    desktop = desktop_name(u.GetThreadDesktop(k.GetCurrentThreadId()))
    input_desktop = u.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
    _need(bool(input_desktop), "canvas_input_desktop_query")
    try:
        input_name = desktop_name(input_desktop)
    finally:
        u.CloseDesktop(input_desktop)
    gui = GUITHREADINFO(cbSize=C.sizeof(GUITHREADINFO))
    _need(u.GetGUIThreadInfo(thread, C.byref(gui)), "canvas_focus_query")
    foreground = u.GetForegroundWindow() or 0
    target = (u.WindowFromPoint(W.POINT(*loc)) or 0) if loc is not None else 0
    handles = {main_hwnd, foreground, gui.hwndFocus or 0, target} - {0}
    overflow = False
    observed, hidden_omitted = 0, 0
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def visit(hwnd, _):
        nonlocal overflow, observed, hidden_omitted
        observed += 1
        if observed > 4096:
            overflow = True
            return False
        if hwnd not in handles and not u.IsWindowVisible(hwnd):
            hidden_omitted += 1
            return True
        if len(handles) >= 260:
            overflow = True
            return False
        handles.add(hwnd)
        return True
    api(u, "EnumChildWindows", W.BOOL, W.HWND, callback_type, W.LPARAM)
    u.EnumChildWindows(main_hwnd, visit, 0)
    rows = []
    for hwnd in sorted(handles):
        owner = W.DWORD()
        tid = u.GetWindowThreadProcessId(hwnd, C.byref(owner))
        name, title = C.create_unicode_buffer(257), C.create_unicode_buffer(513)
        _need(u.GetClassNameW(hwnd, name, len(name)) > 0, "canvas_class_query")
        if owner.value == app_pid:
            u.GetWindowTextW(hwnd, title, len(title))
        rect, client = W.RECT(), W.RECT()
        _need(u.GetWindowRect(hwnd, C.byref(rect)) and u.GetClientRect(hwnd, C.byref(client)), "canvas_rect_query")
        rows.append({"hwnd": hwnd, "pid": owner.value, "thread_id": tid, "class": name.value,
            "title": title.value, "parent": u.GetParent(hwnd) or 0, "root_hwnd": u.GetAncestor(hwnd, 2) or 0,
            "is_main_child": bool(u.IsChild(main_hwnd, hwnd)), "exists": bool(u.IsWindow(hwnd)),
            "visible": bool(u.IsWindowVisible(hwnd)), "enabled": bool(u.IsWindowEnabled(hwnd)),
            "dpi": u.GetDpiForWindow(hwnd), "rect": [rect.left, rect.top, rect.right, rect.bottom],
            "client_rect": [client.left, client.top, client.right, client.bottom],
            "pixel_format": pixel_format(hwnd) if owner.value == app_pid else
                {"index": 0, "describe_count": 0, "flags": 0, "query_error": "foreign_window"}})
    return {"schema_version": 1, "run_id": run_id, "app_pid": app_pid, "process_created": created,
        "main_hwnd": main_hwnd, "session_id": session.value, "active_session_id": k.WTSGetActiveConsoleSessionId(),
        "thread_desktop": desktop, "input_desktop": input_name, "foreground_hwnd": foreground,
        "focus_hwnd": gui.hwndFocus or 0, "target_hwnd": target, "loc": loc,
        "screen": [u.GetSystemMetrics(0), u.GetSystemMetrics(1)], "complete": not overflow,
        "census_scope": "visible_descendants_and_identity", "observed_windows": observed,
        "hidden_omitted": hidden_omitted,
        "captured_monotonic_ns": observation_started, "observation_finished_ns": time.monotonic_ns(), "windows": rows,
        "opengl_candidates": [r["hwnd"] for r in rows if r["pid"] == app_pid and
            r["is_main_child"] and r["pixel_format"]["index"] > 0 and
            r["pixel_format"]["describe_count"] >= r["pixel_format"]["index"] and
            r["pixel_format"]["flags"] & 0x24 == 0x24]}


def send_canvas_number(guard, arguments, send_keys):
    """Preserve the ImGui selection made by the preceding guarded Click."""
    for character in arguments["text"]:
        guard.recheck_canvas_keys(arguments)
        send_keys(character, interval=0.04, waitTime=0.05)
    guard.recheck_canvas_keys(arguments)
    send_keys("{Enter}", waitTime=0.05)
