import os
import sys
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass
class MonitorInfo:
    monitor_id: str
    device_name: str
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    is_primary: bool = False

    @property
    def rect(self):
        return (self.left, self.top, self.right, self.bottom)

    @property
    def size(self):
        return (self.width, self.height)


def _is_windows() -> bool:
    return sys.platform == "win32"


class MonitorManager:
    def __init__(self):
        self._monitors: List[MonitorInfo] = []
        self._refresh_monitors()

    def _refresh_monitors(self):
        if not _is_windows():
            self._monitors = [MonitorInfo(
                monitor_id="0",
                device_name="Display",
                left=0, top=0,
                right=1920, bottom=1080,
                width=1920, height=1080,
                is_primary=True
            )]
            return
        self._monitors = self._enum_display_monitors()

    def _enum_display_monitors(self) -> List[MonitorInfo]:
        monitors = []
        user32 = ctypes.windll.user32

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.LPARAM
        )

        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", ctypes.c_wchar * 32),
            ]

        def _monitor_callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            mi = MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(MONITORINFOEX)
            if user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                left = mi.rcMonitor.left
                top = mi.rcMonitor.top
                right = mi.rcMonitor.right
                bottom = mi.rcMonitor.bottom
                monitors.append(MonitorInfo(
                    monitor_id=str(len(monitors)),
                    device_name=mi.szDevice,
                    left=left, top=top,
                    right=right, bottom=bottom,
                    width=right - left,
                    height=bottom - top,
                    is_primary=bool(mi.dwFlags & 1)
                ))
            return 1

        callback_func = MONITORENUMPROC(_monitor_callback)
        user32.EnumDisplayMonitors(None, None, callback_func, 0)

        for i, m in enumerate(monitors):
            m.monitor_id = str(i)
        return monitors

    def get_monitors(self, force_refresh: bool = False) -> List[MonitorInfo]:
        if force_refresh:
            self._refresh_monitors()
        return list(self._monitors)

    def get_primary_monitor(self) -> Optional[MonitorInfo]:
        for m in self._monitors:
            if m.is_primary:
                return m
        return self._monitors[0] if self._monitors else None

    def get_monitor_by_id(self, monitor_id: str) -> Optional[MonitorInfo]:
        for m in self._monitors:
            if m.monitor_id == monitor_id:
                return m
        return None

    def count(self) -> int:
        return len(self._monitors)
