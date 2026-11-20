"""Optional WDDM process counters. Absence of an owned instance stays unknown."""

from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import math

from .perf_win32 import _api


class _Value(C.Union):
    _fields_ = [("value", C.c_double), ("storage", C.c_longlong)]


class _CounterValue(C.Structure):
    _fields_ = [("status", W.DWORD), ("data", _Value)]


class _Item(C.Structure):
    _fields_ = [("name", W.LPWSTR), ("counter", _CounterValue)]


_pdh = C.WinDLL("pdh")
_open = _api(_pdh, "PdhOpenQueryW", W.DWORD, W.LPCWSTR, C.c_size_t, C.POINTER(W.HANDLE))
_add = _api(_pdh, "PdhAddEnglishCounterW", W.DWORD, W.HANDLE, W.LPCWSTR,
            C.c_size_t, C.POINTER(W.HANDLE))
_collect = _api(_pdh, "PdhCollectQueryData", W.DWORD, W.HANDLE)
_array = _api(_pdh, "PdhGetFormattedCounterArrayW", W.DWORD, W.HANDLE, W.DWORD,
              C.POINTER(W.DWORD), C.POINTER(W.DWORD), C.c_void_p)
_close = _api(_pdh, "PdhCloseQuery", W.DWORD, W.HANDLE)

_MORE_DATA = 0x800007D2
_FORMAT_DOUBLE = 0x00000200 | 0x00001000  # PDH_FMT_DOUBLE | PDH_FMT_NOSCALE
_PATHS = {
    "gpu_engine_pct": r"\GPU Engine(*)\Utilization Percentage",
    "gpu_dedicated_mb": r"\GPU Process Memory(*)\Dedicated Usage",
    "gpu_shared_mb": r"\GPU Process Memory(*)\Shared Usage",
}


class GpuCounters:
    def __init__(self, pid):
        self.prefix = f"pid_{pid}_"
        self.query = W.HANDLE()
        self.counters = {}
        if _open(None, 0, C.byref(self.query)) != 0:
            raise OSError("PDH query unavailable")
        for name, path in _PATHS.items():
            counter = W.HANDLE()
            if _add(self.query, path, 0, C.byref(counter)) == 0:
                self.counters[name] = counter

    def close(self):
        _close(self.query)

    def _values(self, counter):
        size, count = W.DWORD(), W.DWORD()
        if _array(counter, _FORMAT_DOUBLE, C.byref(size), C.byref(count), None) != _MORE_DATA:
            return []
        for _ in range(2):
            if not 0 < size.value <= 8 * 1024 * 1024:
                return []
            buffer = C.create_string_buffer(size.value)
            status = _array(counter, _FORMAT_DOUBLE, C.byref(size), C.byref(count), buffer)
            if status == _MORE_DATA:  # instances can appear between calls
                continue
            if status or count.value * C.sizeof(_Item) > len(buffer):
                return []
            values = []
            for item in (_Item * count.value).from_buffer(buffer):
                if (item.name and item.name.casefold().startswith(self.prefix)
                        and item.counter.status in (0, 1)):
                    value = item.counter.data.value
                    if math.isfinite(value) and value >= 0:
                        values.append(value)
            return values
        return []

    def snapshot(self):
        if not self.counters or _collect(self.query) != 0:
            return {}
        result = {}
        for name, counter in self.counters.items():
            values = self._values(counter)
            if values:
                result[name] = (max(values) if name == "gpu_engine_pct"
                                else sum(values) / (1024 * 1024))
        return result
