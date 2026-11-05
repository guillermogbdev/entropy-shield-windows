"""Single-instance guard for the GUI and for the elevated helper.

A named kernel mutex is released automatically when the process exits, even
after a crash, so it is a better fit on Windows than the Linux flock file.
"""
from __future__ import annotations

import ctypes
import getpass
import re

_ERROR_ALREADY_EXISTS = 183
_handles: dict[str, int] = {}


def acquire(name: str) -> bool:
    """Create *name*; return False if another process already owns it."""
    if name in _handles:
        return True
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
    mutex_name = f"Local\\EntropyShield-{name}-{user}"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        return False
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _handles[name] = handle
    return True


def release(name: str) -> None:
    handle = _handles.pop(name, None)
    if handle:
        try:
            ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            pass
