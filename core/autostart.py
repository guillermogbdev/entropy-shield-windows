from __future__ import annotations
import os
import subprocess
import sys

_DESKTOP_NAME = "entropy-shield.desktop"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "EntropyShield"

_DESKTOP_CONTENT = """\
[Desktop Entry]
Name=Entropy Shield
Comment=Network Privacy Stack — Tor, DNSCrypt, I2P
Exec=entropy-shield --tray
Icon=/usr/share/pixmaps/entropy-shield.png
Type=Application
Categories=Network;Security;
Terminal=false
StartupWMClass=entropy-shield
X-GNOME-Autostart-enabled=true
"""


# ── Linux (XDG autostart) ───────────────────────────────────────────────────

def _autostart_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "autostart")


def _desktop_path() -> str:
    return os.path.join(_autostart_dir(), _DESKTOP_NAME)


# ── Windows (HKCU Run key) ──────────────────────────────────────────────────

def _windows_command() -> str:
    if getattr(sys, "frozen", False):
        argv = [sys.executable, "--tray"]
    else:
        exe = sys.executable
        try:
            from pathlib import Path
            pythonw = Path(exe).with_name("pythonw.exe")
            if pythonw.is_file():
                exe = str(pythonw)
        except Exception:
            pass
        main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        argv = [exe, main_py, "--tray"]
    return subprocess.list2cmdline(argv)


def _win_enable() -> bool:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, _windows_command())
        return True
    except Exception:
        return False


def _win_disable() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, _RUN_VALUE)
            except FileNotFoundError:
                pass
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def _win_is_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
            return bool(value)
    except Exception:
        return False


# ── public API ─────────────────────────────────────────────────────────────

def enable() -> bool:
    if os.name == "nt":
        return _win_enable()
    try:
        adir = _autostart_dir()
        os.makedirs(adir, exist_ok=True)
        with open(_desktop_path(), "w") as f:
            f.write(_DESKTOP_CONTENT)
        return True
    except Exception:
        return False


def disable() -> bool:
    if os.name == "nt":
        return _win_disable()
    try:
        path = _desktop_path()
        if os.path.exists(path):
            os.unlink(path)
        return True
    except Exception:
        return False


def is_enabled() -> bool:
    if os.name == "nt":
        return _win_is_enabled()
    return os.path.exists(_desktop_path())
