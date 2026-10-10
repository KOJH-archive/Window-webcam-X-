"""Read only idle duration and foreground process identity from Windows."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

import psutil


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def idle_seconds() -> float | None:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    user32 = ctypes.windll.user32
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    # Both counters wrap at 2^32 milliseconds.
    tick = ctypes.windll.kernel32.GetTickCount() & 0xffffffff
    return ((tick - info.dwTime) & 0xffffffff) / 1000


def foreground_process() -> str | None:
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    try:
        return psutil.Process(pid.value).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def foreground_fullscreen() -> bool:
    process = foreground_process()
    if process is None or process in {"explorer.exe", "dwm.exe", "shellexperiencehost.exe"}:
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return False
    # A normal maximized window is work, not a full-screen presentation.
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    if user32.GetWindowLongW(hwnd, -16) & 0x00C00000:
        return False
    window = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window)):
        return False
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if not monitor:
        return False

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    screen = info.rcMonitor
    return (window.left <= screen.left + 2 and window.top <= screen.top + 2 and
            window.right >= screen.right - 2 and window.bottom >= screen.bottom - 2)


def protected_process_running(names: tuple[str, ...]) -> bool:
    if not names:
        return False
    wanted = set(names)
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").lower() in wanted:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


class ForegroundSwitches:
    def __init__(self):
        self.previous: str | None = None
        self.events: list[float] = []

    def update(self, now: float, process: str | None) -> int:
        self.events = [at for at in self.events if now - at < 60]
        if process is not None:
            if self.previous is not None and process != self.previous:
                self.events.append(now)
            self.previous = process
        return len(self.events)

    def reset(self):
        self.previous = None
        self.events.clear()
