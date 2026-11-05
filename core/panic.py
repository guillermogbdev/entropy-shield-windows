"""Panic / Emergency wipe helpers (user-space, no root required).

On Windows the privileged work is done by the helper, but this module also
tries the repair paths directly so a panic still helps if the helper is gone.
"""
from __future__ import annotations
import os
import subprocess


def flush_dns_cache() -> None:
    """Try every known DNS cache flush method."""
    if os.name == "nt":
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
        return
    for cmd in (
        ["resolvectl", "flush-caches"],
        ["systemd-resolve", "--flush-caches"],
        ["nscd", "-i", "hosts"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
        except Exception:
            pass


def clear_proxy_env() -> None:
    """Remove proxy env vars from the current process environment."""
    for var in (
        "ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy",
        "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
        "NO_PROXY", "no_proxy",
    ):
        os.environ.pop(var, None)


def clear_temp_traces() -> None:
    """Remove entropy-shield proxy env files written to disk."""
    if os.name == "nt":
        try:
            from core.windows import netconfig
            netconfig.restore_system_dns()
            netconfig.restore_system_proxy()
        except Exception:
            pass
        return
    _env_file = os.path.expanduser(
        "~/.config/environment.d/entropy-shield-proxy.conf"
    )
    for path in (
        _env_file,
        "/etc/profile.d/entropy-shield-proxy.sh",
        "/etc/fish/conf.d/entropy-shield-proxy.fish",
    ):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass


def user_space_panic(log_fn=None) -> None:
    """Everything we can do without root: flush DNS, clear env, remove files."""
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    _log("[PANIC] Flushing DNS cache…")
    flush_dns_cache()

    _log("[PANIC] Clearing proxy environment variables…")
    clear_proxy_env()

    if os.name == "nt":
        _log("[PANIC] Restoring system DNS and proxy settings…")
        try:
            from core.windows.firewall import WindowsFirewallManager
            WindowsFirewallManager(_log).heal()
        except Exception:
            pass
    else:
        _log("[PANIC] Removing proxy env files…")
    clear_temp_traces()

    _log("[PANIC] User-space cleanup complete.")
