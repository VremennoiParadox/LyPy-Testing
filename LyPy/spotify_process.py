"""Detect Spotify.exe without extra dependencies (Windows only)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


def spotify_exe_running() -> bool:
    """Return True if any process named Spotify.exe is in the snapshot."""
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    INVALID = ctypes.c_void_p(-1).value

    k32 = ctypes.windll.kernel32
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID or snap == 0:
        return False
    try:
        if not k32.Process32FirstW(snap, ctypes.byref(pe)):
            return False
        while True:
            if pe.szExeFile.lower() == "spotify.exe":
                return True
            if not k32.Process32NextW(snap, ctypes.byref(pe)):
                break
    finally:
        k32.CloseHandle(snap)
    return False
