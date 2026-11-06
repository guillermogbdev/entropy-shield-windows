"""Single-instance guard for the GUI and for the elevated helper.

A named kernel mutex is released automatically when the process exits, even
after a crash, so it is a better fit on Windows than the Linux flock file.

The mutex alone produced a confusing failure: closing the window only hides the
app to the notification area, so clicking the shortcut again started a second
process that found the mutex and exited silently - nothing appeared on screen
and the only workaround was rebooting.  A named auto-reset event lets that
second process ask the running one to restore its window.
"""
from __future__ import annotations

import ctypes
import getpass
import re

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SW_RESTORE = 9

_handles: dict[str, int] = {}
_events: dict[str, int] = {}


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _names(name: str) -> tuple[str, str]:
    """Return the (mutex, activation-event) names for *name*.

    ``Local\\`` keeps the objects in the current session and the user name keeps
    them per-account, so two users can each run their own instance.
    """
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
    base = f"Local\\EntropyShield-{name}-{user}"
    return base, base + "-activate"


def acquire(name: str) -> bool:
    """Create *name*; return False if another process already owns it."""
    if name in _handles:
        return True
    kernel32 = _kernel32()
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                      ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                      ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateEventW.restype = ctypes.c_void_p

    mutex_name, event_name = _names(name)
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        return False
    already = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
    if already:
        kernel32.CloseHandle(handle)
        return False

    # Auto-reset event: every SetEvent() wakes exactly one consumer, so two
    # quick double-clicks cannot leave a stale "show" request behind.
    event = kernel32.CreateEventW(None, False, False, event_name)
    if event:
        _events[name] = event
    _handles[name] = handle
    return True


def request_activation(name: str) -> bool:
    """Ask the running instance to show its window.

    Returns True when the running instance was signalled.  False means no
    activation event exists (an older build, or a different session/user).
    """
    kernel32 = _kernel32()
    kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_bool,
                                    ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.SetEvent.restype = ctypes.c_bool

    _, event_name = _names(name)
    handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, event_name)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def consume_activation(name: str) -> bool:
    """Return True once for every request_activation() from another process."""
    handle = _events.get(name)
    if not handle:
        return False
    kernel32 = _kernel32()
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    return kernel32.WaitForSingleObject(handle, 0) == 0


def _process_image(pid: int) -> str:
    kernel32 = _kernel32()
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool,
                                     ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_uint32)]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_uint32(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                               ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def activate_existing_window() -> bool:
    """Fallback for instances that predate the activation event.

    Finds a top-level window owned by Entropy Shield.exe and restores it.  Used
    when the named event cannot be opened (older build, elevated instance in a
    different integrity level).
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]

    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _visit(hwnd, _lparam) -> bool:
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        image = _process_image(pid.value).lower()
        if not image.endswith("entropy shield.exe"):
            return True
        # Hidden windows still have a title; skip helper/tool windows.
        if user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        found.append(hwnd)
        return True

    user32.EnumWindows(_visit, 0)
    for hwnd in found:
        user32.ShowWindow(hwnd, _SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    return bool(found)


def release(name: str) -> None:
    kernel32 = _kernel32()
    event = _events.pop(name, None)
    if event:
        try:
            kernel32.CloseHandle(ctypes.c_void_p(event))
        except Exception:
            pass
    handle = _handles.pop(name, None)
    if handle:
        try:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            pass
