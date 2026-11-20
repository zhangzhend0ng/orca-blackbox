"""Owned process tree using a non-breakaway, kill-on-close Windows Job.

Create suspended -> assign Job -> resume. No process-name sweeps or shell.
ActiveProcesses==0 is the only descendant-quiescence receipt. References:
learn.microsoft.com/windows/win32/procthread/job-objects and jobapi2 APIs.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess


class _BasicLimits(C.Structure):
    _fields_ = [("ProcessTime", C.c_longlong), ("JobTime", C.c_longlong),
                ("Flags", W.DWORD), ("MinWorkingSet", C.c_size_t),
                ("MaxWorkingSet", C.c_size_t), ("ActiveLimit", W.DWORD),
                ("Affinity", C.c_size_t), ("Priority", W.DWORD),
                ("Scheduling", W.DWORD)]


class _IO(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in
                ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]


class _ExtendedLimits(C.Structure):
    _fields_ = [("Basic", _BasicLimits), ("IO", _IO),
                ("ProcessMemory", C.c_size_t), ("JobMemory", C.c_size_t),
                ("PeakProcessMemory", C.c_size_t), ("PeakJobMemory", C.c_size_t)]


class _Accounting(C.Structure):
    _fields_ = [(name, C.c_longlong) for name in ("User", "Kernel", "PeriodUser", "PeriodKernel")] + [
        (name, W.DWORD) for name in ("Faults", "Total", "Active", "Terminated")]


def current_job_process_ids() -> set[int]:
    """Read the member PIDs of this worker's immediate Job, including nested jobs."""
    query = C.WinDLL("kernel32", use_last_error=True).QueryInformationJobObject
    query.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p]
    query.restype = W.BOOL
    capacity = 32
    while capacity <= 32768:
        class ProcessList(C.Structure):
            _fields_ = [("assigned", W.DWORD), ("listed", W.DWORD),
                        ("pids", C.c_size_t * capacity)]

        members = ProcessList()
        if query(None, 3, C.byref(members), C.sizeof(members), None):
            if members.assigned == members.listed:
                return set(members.pids[:members.listed])
        elif C.get_last_error() != 234:  # ERROR_MORE_DATA
            raise C.WinError(C.get_last_error())
        capacity = max(capacity * 2, members.assigned)
    raise OSError("Job member list exceeds sample capacity")


class OwnedJobProcess:
    """Trusted low-level adapter. Keep handles open until query confirms zero."""

    @classmethod
    def start(cls, argv: list[str], *, cwd: Path, log_path: Path, env: dict[str, str]):
        if os.name != "nt":
            raise OSError("Windows Job Objects required")
        import _winapi
        import msvcrt
        self = cls.__new__(cls)
        self._api = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([C.c_void_p, W.LPCWSTR], W.HANDLE),
            "SetInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            "AssignProcessToJobObject": ([W.HANDLE, W.HANDLE], W.BOOL),
            "QueryInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            "TerminateJobObject": ([W.HANDLE, W.UINT], W.BOOL),
            "ResumeThread": ([W.HANDLE], W.DWORD),
        }
        for name, (args, ret) in signatures.items():
            func = getattr(self._api, name)
            func.argtypes, func.restype = args, ret
        self._job = self._api.CreateJobObjectW(None, None)
        if not self._job:
            raise C.WinError(C.get_last_error())
        self._process = None
        self._closed = False
        self._log = None
        thread = None
        try:
            limits = _ExtendedLimits()
            limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            self._check(self._api.SetInformationJobObject(self._job, 9, C.byref(limits), C.sizeof(limits)))
            self._log = log_path.open("xb")
            with open(os.devnull, "rb") as null:
                stdout = msvcrt.get_osfhandle(self._log.fileno())
                stdin = msvcrt.get_osfhandle(null.fileno())
                si = subprocess.STARTUPINFO()
                si.dwFlags = _winapi.STARTF_USESTDHANDLES
                si.hStdInput, si.hStdOutput, si.hStdError = stdin, stdout, stdout
                si.lpAttributeList = {"handle_list": [stdin, stdout]}
                os.set_handle_inheritable(stdin, True)
                os.set_handle_inheritable(stdout, True)
                try:
                    self._process, thread, self.pid, _tid = _winapi.CreateProcess(
                        argv[0], subprocess.list2cmdline(argv), None, None, True,
                        0x4 | 0x400, env, str(cwd), si)  # suspended + unicode environment
                finally:
                    os.set_handle_inheritable(stdin, False)
                    os.set_handle_inheritable(stdout, False)
            self._check(self._api.AssignProcessToJobObject(self._job, self._process))
            if self._api.ResumeThread(thread) == 0xFFFFFFFF:
                raise C.WinError(C.get_last_error())
            _winapi.CloseHandle(thread)
            thread = None
            return self
        except BaseException as original:
            # A start failure is quarantined by runtime. Stop only our suspended child/job.
            for action in ([lambda: _winapi.TerminateProcess(self._process, 1)] if self._process else []):
                try:
                    action()
                except OSError:
                    original.add_note("owned suspended process termination could not be confirmed")
            for handle in (thread, self._process, self._job):
                if handle:
                    try:
                        _winapi.CloseHandle(handle)
                    except OSError:
                        original.add_note("owned Windows handle close failed")
            if self._log is not None:
                try:
                    self._log.close()
                except OSError:
                    original.add_note("owned stdout close failed")
            raise

    @staticmethod
    def _check(ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    def poll(self) -> tuple[int | None, int]:
        import _winapi
        if self._closed:
            raise RuntimeError("owned job already closed")
        info = _Accounting()
        self._check(self._api.QueryInformationJobObject(self._job, 1, C.byref(info), C.sizeof(info), None))
        exited = _winapi.WaitForSingleObject(self._process, 0) == _winapi.WAIT_OBJECT_0
        return (_winapi.GetExitCodeProcess(self._process) if exited else None, int(info.Active))

    def terminate(self) -> None:
        if not self._closed:
            self._check(self._api.TerminateJobObject(self._job, 1))

    def close(self) -> None:
        import _winapi
        if not self._closed:
            if self.poll()[1] != 0:
                raise RuntimeError("cannot close unconfirmed active job")
            _winapi.CloseHandle(self._process)
            _winapi.CloseHandle(self._job)
            self._log.close()
            self._closed = True
