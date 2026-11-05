"""Filesystem and executable discovery for the Windows build.

Nothing here needs Administrator rights.  The elevated helper uses the same
paths as the GUI, because UAC elevation keeps the same user profile.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Directory abbreviations used by the installers on Windows.
_ENV_BASES = (
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
)


def app_root() -> Path:
    """The checkout / installation directory that contains ``main.py``."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bin_dir() -> Path:
    return app_root() / "bin"


def config_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "entropy-shield"
    return Path.home() / "AppData" / "Roaming" / "entropy-shield"


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "entropy-shield"
    return Path.home() / "AppData" / "Local" / "entropy-shield"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)


def no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def run(cmd, *, timeout: float | None = None, text: bool = False,
        capture: bool = True):
    """``subprocess.run`` without a flashing console window."""
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=text,
        timeout=timeout,
        creationflags=no_window_flags(),
    )


def popen(cmd, **kwargs):
    kwargs.setdefault("creationflags", no_window_flags())
    return subprocess.Popen(cmd, **kwargs)


def _config_binary(key: str) -> str:
    """Read a user override from config.json without importing config at load."""
    try:
        from core.config import cfg
        value = cfg().get("binaries", key)
        return value.strip() if isinstance(value, str) else ""
    except Exception:
        return ""


def _candidate_paths(name: str) -> list[Path]:
    """Common install locations for *name* (``tor.exe`` etc.)."""
    name_l = name.lower()
    out: list[Path] = []

    if name_l == "tor.exe":
        roots = [
            bin_dir() / "tor",
            bin_dir(),
            bin_dir() / "tor-expert-bundle",
            bin_dir() / "Tor",
        ]
        for root in roots:
            out.append(root / "tor.exe")
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            out += [
                Path(base) / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
                Path(base) / "Tor Browser" / "Tor" / "tor.exe",
                Path(base) / "Programs" / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            ]
        home = Path.home()
        for sub in ("Desktop", "Downloads", "Documents"):
            out += [
                home / sub / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
                home / sub / "tor-browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            ]
    elif name_l == "dnscrypt-proxy.exe":
        out += [
            bin_dir() / "dnscrypt-proxy" / name,
            bin_dir() / name,
            bin_dir() / "dnscrypt-proxy-win64" / name,
        ]
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            base = os.environ.get(env)
            if base:
                out.append(Path(base) / "dnscrypt-proxy" / name)
        out.append(Path.home() / "scoop" / "apps" / "dnscrypt-proxy" / "current" / name)
    elif name_l == "i2pd.exe":
        out += [
            bin_dir() / "i2pd" / name,
            bin_dir() / name,
            bin_dir() / "i2pd_win64" / name,
        ]
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                out.append(Path(base) / "i2pd" / name)
        out.append(Path.home() / "scoop" / "apps" / "i2pd" / "current" / name)

    # A shallow recursive search in bin/ catches extracted archives whose
    # top-level folder has a version in its name.
    try:
        for p in bin_dir().rglob(name):
            out.append(p)
    except OSError:
        pass
    return out


def find_binary(name: str, config_key: str | None = None) -> str | None:
    """Return an absolute path to *name*, or ``None``.

    Search order: explicit environment variable, config.json override, the
    application's ``bin`` directory, common installation folders, then PATH.
    """
    env_name = "ENTROPY_SHIELD_" + name.replace(".exe", "").replace("-", "_").upper()
    for raw in (os.environ.get(env_name), _config_binary(config_key or "")):
        if raw:
            p = Path(os.path.expandvars(raw)).expanduser()
            if p.is_file():
                return str(p)

    for p in _candidate_paths(name):
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass

    found = shutil.which(name)
    return found


def find_obfs4proxy(tor_path: str | None = None) -> str | None:
    """Locate obfs4proxy.exe, preferably next to Tor / in Tor Browser."""
    names = ("obfs4proxy.exe", "lyrebird.exe")
    search_roots: list[Path] = [bin_dir(), bin_dir() / "tor"]
    if tor_path:
        tor = Path(tor_path)
        search_roots += [
            tor.parent,
            tor.parent / "PluggableTransports",
            tor.parent / "pluggable_transports",
            tor.parent.parent / "PluggableTransports",
            tor.parent.parent / "pluggable_transports",
        ]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            search_roots += [
                Path(base) / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "PluggableTransports",
                Path(base) / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "pluggable_transports",
                Path(base) / "Tor Browser" / "Browser" / "TorBrowser" / "Tor",
            ]
    for name in names:
        for root in search_roots:
            p = root / name
            try:
                if p.is_file():
                    return str(p)
            except OSError:
                pass
        # Archive layouts vary; a shallow recursive search is reliable.
        try:
            for p in bin_dir().rglob(name):
                if p.is_file():
                    return str(p)
        except OSError:
            pass
        found = shutil.which(name)
        if found:
            return found
    return None


def find_meek_client(tor_path: str | None = None) -> str | None:
    if tor_path:
        tor = Path(tor_path)
        for root in (tor.parent / "PluggableTransports", tor.parent):
            for name in ("meek-client.exe", "meek-client-torbrowser.exe"):
                p = root / name
                if p.is_file():
                    return str(p)
    return shutil.which("meek-client.exe")


def find_proxybridge() -> str | None:
    """Locate ``ProxyBridge_CLI.exe`` (WinDivert transparent redirector).

    The installer drops the whole application in one folder, so the CLI,
    ``ProxyBridgeCore.dll`` and ``WinDivert`` must stay together.  We return the
    CLI path and the caller uses its parent as the working directory.
    """
    override = _config_binary("proxybridge")
    if override:
        p = Path(os.path.expandvars(override)).expanduser()
        if p.is_file():
            return str(p)
    env = os.environ.get("ENTROPY_SHIELD_PROXYBRIDGE")
    if env:
        p = Path(os.path.expandvars(env)).expanduser()
        if p.is_file():
            return str(p)

    data = data_dir()
    candidates: list[Path] = [
        data / "proxybridge" / "ProxyBridge_CLI.exe",
        bin_dir() / "proxybridge" / "ProxyBridge_CLI.exe",
        bin_dir() / "ProxyBridge" / "ProxyBridge_CLI.exe",
    ]
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)",
                     "ProgramData"):
        base = os.environ.get(env_name)
        if not base:
            continue
        candidates += [
            Path(base) / "ProxyBridge" / "ProxyBridge_CLI.exe",
            Path(base) / "Programs" / "ProxyBridge" / "ProxyBridge_CLI.exe",
        ]
    for p in candidates:
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass
    return shutil.which("ProxyBridge_CLI.exe")


def find_firefox() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Mozilla Firefox" / "firefox.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Mozilla Firefox" / "firefox.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Mozilla Firefox" / "firefox.exe",
    ]
    for p in candidates:
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass
    return shutil.which("firefox.exe")


def find_chromium() -> tuple[str, str] | None:
    """Return (path, kind) for Edge / Chrome / Brave / Chromium."""
    candidates = [
        (Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe", "edge"),
        (Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe", "edge"),
        (Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"),
        (Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"),
        (Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"),
        (Path(os.environ.get("ProgramFiles", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe", "brave"),
        (Path(os.environ.get("ProgramFiles(x86)", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe", "brave"),
    ]
    for p, kind in candidates:
        try:
            if p.is_file():
                return str(p), kind
        except OSError:
            pass
    for name in ("msedge.exe", "chrome.exe", "brave.exe", "chromium.exe"):
        found = shutil.which(name)
        if found:
            return found, name.split(".")[0]
    return None


def find_any_browser() -> tuple[str, str] | None:
    """Return (path, kind) where kind is ``firefox`` or a Chromium flavour."""
    ff = find_firefox()
    if ff:
        return ff, "firefox"
    return find_chromium()
