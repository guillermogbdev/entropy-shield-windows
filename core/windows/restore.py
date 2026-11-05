"""Non-interactive recovery entry point for the Windows build.

This is what ``scripts/restore-windows.ps1`` and ``scripts/uninstall-windows.ps1``
call through the frozen EXE (``Entropy Shield.exe --windows-restore``).  Doing
the work inside the application means recovery also works on machines that do
not have Python installed.

It is safe to run more than once: every operation is a no-op unless a snapshot
from a previous session exists.
"""
from __future__ import annotations

import sys
import time

from . import netconfig, paths
from .admin import is_admin
from .client import shutdown_existing
from .firewall import WindowsFirewallManager


def _log(message: str) -> None:
    """Print when a console exists and always append to restore.log."""
    try:
        print(message, flush=True)
    except Exception:
        pass
    try:
        paths.ensure_dirs()
        log_file = paths.data_dir() / "restore.log"
        try:
            if log_file.exists() and log_file.stat().st_size > 1024 * 1024:
                log_file.replace(log_file.with_suffix(".log.1"))
        except OSError:
            pass
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def main() -> int:
    if not is_admin():
        _log("[ERR] Restore must run as Administrator.")
        return 1

    _log("[RESTORE] Starting Windows network recovery…")

    # If a helper is still alive (but idle), ask it to disconnect and exit.
    # A helper with an active session cannot be reached because its server is
    # single-threaded; in that case the watchdog may re-apply the kill switch,
    # so the user should close the GUI first.
    try:
        shutdown_existing(timeout=5.0)
    except Exception as exc:
        _log(f"[RESTORE] Could not stop a running helper: {exc}")

    firewall_ok = False
    try:
        firewall_ok = WindowsFirewallManager(_log).heal()
    except Exception as exc:
        _log(f"[ERR] Firewall restore failed: {exc}")

    try:
        network_ok = netconfig.heal(_log)
    except Exception as exc:
        _log(f"[ERR] DNS/proxy restore failed: {exc}")
        network_ok = False

    if firewall_ok and network_ok:
        _log("[RESTORE] Firewall, DNS and proxy settings restored.")
        return 0

    _log("[ERR] One or more settings could not be restored. The snapshot was "
         "kept; run this again after closing Entropy Shield, or reboot.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
