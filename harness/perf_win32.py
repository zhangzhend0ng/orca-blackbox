"""Windows counters for the optional performance sampler."""

from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W


class _Memory(C.Structure):
    _fields_ = [
        ("cb", W.DWORD), ("PageFaultCount", W.DWORD),
        *[(name, C.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
        )],
    ]


def _api(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


_kernel = C.WinDLL("kernel32", use_last_error=True)
_user = C.WinDLL("user32", use_last_error=True)
_open = _api(_kernel, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
_close = _api(_kernel, "CloseHandle", W.BOOL, W.HANDLE)
_times = _api(_kernel, "GetProcessTimes", W.BOOL, W.HANDLE, *([C.POINTER(W.FILETIME)] * 4))
_exit_code = _api(_kernel, "GetExitCodeProcess", W.BOOL, W.HANDLE, C.POINTER(W.DWORD))
_memory = _api(_kernel, "K32GetProcessMemoryInfo", W.BOOL, W.HANDLE, C.POINTER(_Memory), W.DWORD)
_resources = _api(_user, "GetGuiResources", W.DWORD, W.HANDLE, W.DWORD)


def _filetime(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class Process:
    """Retain a process handle so PID recycling cannot change the target."""

    def __init__(self, pid: int):
        self.handle = _open(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not self.handle:
            raise C.WinError(C.get_last_error())

    def close(self):
        _close(self.handle)

    def resources(self):
        counts = []
        for kind in (0, 1):  # GDI objects, USER objects
            C.set_last_error(0)
            value = _resources(self.handle, kind)
            counts.append(None if value == 0 and C.get_last_error() else int(value))
        return tuple(counts)

    def snapshot(self):
        code = W.DWORD()
        if not _exit_code(self.handle, C.byref(code)):
            raise C.WinError(C.get_last_error())
        if code.value != 259:  # STILL_ACTIVE
            return None
        first, last, kernel, user = (W.FILETIME() for _ in range(4))
        if not _times(self.handle, *(C.byref(t) for t in (first, last, kernel, user))):
            raise C.WinError(C.get_last_error())
        info = _Memory()
        info.cb = C.sizeof(info)
        readable = _memory(self.handle, C.byref(info), info.cb)
        gdi, user_obj = self.resources()
        return (
            _filetime(first),
            (_filetime(kernel) + _filetime(user)) / 10_000_000,
            info.WorkingSetSize if readable else None,
            info.PrivateUsage if readable else None,
            gdi, user_obj,
        )
