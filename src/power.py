"""Windows sleep and resume notifications; power actions are dependency-injected."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import queue


class LUID(C.Structure):
    _fields_ = [("low", W.DWORD), ("high", W.LONG)]


class LuidAttributes(C.Structure):
    _fields_ = [("luid", LUID), ("attributes", W.DWORD)]


class TokenPrivileges(C.Structure):
    _fields_ = [("count", W.DWORD), ("privileges", LuidAttributes * 1)]


CALLBACK = C.WINFUNCTYPE(W.DWORD, C.c_void_p, W.DWORD, C.c_void_p)


class Subscription(C.Structure):
    _fields_ = [("callback", CALLBACK), ("context", C.c_void_p)]


def windows_sleep(lock_before: bool = False) -> bool:
    kernel = C.WinDLL("kernel32", use_last_error=True)
    advapi = C.WinDLL("advapi32", use_last_error=True)
    powrprof = C.WinDLL("powrprof", use_last_error=True)
    user32 = C.WinDLL("user32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    advapi.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
    advapi.LookupPrivilegeValueW.argtypes = [W.LPCWSTR, W.LPCWSTR, C.POINTER(LUID)]
    advapi.AdjustTokenPrivileges.argtypes = [W.HANDLE, W.BOOL, C.POINTER(TokenPrivileges), W.DWORD,
                                             C.POINTER(TokenPrivileges), C.POINTER(W.DWORD)]
    powrprof.SetSuspendState.argtypes = [C.c_ubyte, C.c_ubyte, C.c_ubyte]
    powrprof.SetSuspendState.restype = C.c_ubyte
    user32.LockWorkStation.restype = W.BOOL
    token = W.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x20 | 0x8, C.byref(token)):
        return False
    previous = TokenPrivileges()
    try:
        state = TokenPrivileges()
        state.count = 1
        if not advapi.LookupPrivilegeValueW(None, "SeShutdownPrivilege", C.byref(state.privileges[0].luid)):
            return False
        state.privileges[0].attributes = 2
        size = W.DWORD()
        C.set_last_error(0)
        if not advapi.AdjustTokenPrivileges(token, False, C.byref(state), C.sizeof(previous),
                                            C.byref(previous), C.byref(size)) or C.get_last_error() == 1300:
            return False
        if lock_before and not user32.LockWorkStation():
            return False
        C.set_last_error(0)
        return bool(powrprof.SetSuspendState(0, 0, 0))
    finally:
        if previous.count:
            advapi.AdjustTokenPrivileges(token, False, C.byref(previous), 0, None, None)
        kernel.CloseHandle(token)


class PowerMonitor:
    """Registered callback remains alive until close(); queue is consumed by main loop."""
    def __init__(self):
        self.queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.library = C.WinDLL("powrprof", use_last_error=True)
        self.library.PowerRegisterSuspendResumeNotification.argtypes = [W.DWORD, C.c_void_p, C.POINTER(W.HANDLE)]
        self.library.PowerRegisterSuspendResumeNotification.restype = W.DWORD
        self.library.PowerUnregisterSuspendResumeNotification.argtypes = [W.HANDLE]
        self.library.PowerUnregisterSuspendResumeNotification.restype = W.DWORD
        self.callback = CALLBACK(self._on_event)
        self.subscription = Subscription(self.callback, None)
        self.handle = W.HANDLE()
        code = self.library.PowerRegisterSuspendResumeNotification(2, C.byref(self.subscription), C.byref(self.handle))
        if code:
            raise OSError(code, "PowerRegisterSuspendResumeNotification failed")

    def _on_event(self, context, event_type, setting):
        if event_type == 4:
            self.queue.put("suspend")
        elif event_type in (7, 18):
            self.queue.put("resume")
        return 0

    def close(self):
        if self.handle and self.handle.value:
            self.library.PowerUnregisterSuspendResumeNotification(self.handle)
            self.handle = W.HANDLE()


class SleepController:
    def __init__(self, release_camera, reopen_camera, record_event, *, sleep_fn=windows_sleep,
                 dry_run: bool = True, lock_before: bool = False):
        self.release_camera = release_camera
        self.reopen_camera = reopen_camera
        self.record_event = record_event
        self.sleep_fn = sleep_fn
        self.dry_run = dry_run
        self.lock_before = lock_before

    def suspend(self) -> str:
        requested_at = datetime.now(timezone.utc)
        if self.dry_run:
            self.record_event("sleep_dry_run", at=requested_at)
            return "dry_run"
        self.record_event("sleep_request", at=requested_at)
        if not self.release_camera():
            self.record_event("sleep_failed", "camera_release")
            return "failed"
        try:
            success = self.sleep_fn(self.lock_before)
        except Exception:
            success = False
        if success:
            self.record_event("sleep", at=requested_at)
            return "sleep"
        self.record_event("sleep_failed", "power_api")
        self.reopen_camera()
        return "failed"
