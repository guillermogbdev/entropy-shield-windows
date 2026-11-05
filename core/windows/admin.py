"""UAC helpers.

The GUI deliberately stays at the normal user's integrity level.  The small
helper process that touches the firewall and the system DNS is started with
``runas`` only when it is needed.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _python_for_helper() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    p = Path(sys.executable)
    pythonw = p.with_name("pythonw.exe")
    return str(pythonw) if pythonw.is_file() else sys.executable


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _helper_arguments() -> str:
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline(["--windows-helper"])
    return subprocess.list2cmdline(["-m", "core.windows.daemon_win"])


def start_helper() -> tuple[bool, str]:
    """Start the elevated helper with UAC.  Returns (started, message).

    ``ShellExecuteW`` returns a value > 32 on success.  The caller still has to
    wait for the helper's control file, because UAC may be slow.
    """
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            _python_for_helper(),
            _helper_arguments(),
            _app_root(),
            0,  # SW_HIDE
        )
    except Exception as exc:
        return False, f"Could not start the privileged helper: {exc}"
    if rc <= 32:
        return False, (
            "Administrator permission was not granted. The firewall, DNS and "
            "kill switch need it; the rest of the app cannot connect without it."
        )
    return True, "Privileged helper launched."
