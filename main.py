#!/usr/bin/env python3
from __future__ import annotations
import sys
import os


def _enable_dpi_awareness() -> None:
    """Make the frozen EXE DPI-aware like python.exe is.

    Without this, PyInstaller's default manifest leaves the process
    DPI-unaware: Qt sees a virtual 1280×720 screen, native maximise only fills
    that virtual area, and the window looks half-sized on a 150% display.
    Must run before QApplication creates any window.
    """
    if os.name != "nt":
        return
    import ctypes
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()

# Ensure NixOS system paths are always available (Linux only).
if os.name != "nt":
    for _p in ("/run/current-system/sw/bin", "/run/wrappers/bin",
               "/nix/var/nix/profiles/default/bin"):
        if _p not in os.environ.get("PATH", ""):
            os.environ["PATH"] = _p + ":" + os.environ.get("PATH", "")

# Keep a module-level reference so the lock is held for the entire lifetime
# of the process.  Without this the file handle is GC'd and the lock drops.
_instance_lock = None


def _lock_dir() -> str:
    """Return a private, user-owned directory to hold the single-instance lock.

    Never /tmp: it is world-writable, so on a shared machine another account
    could hold "entropy-shield.lock" open to keep the app from ever starting,
    or point it at a symlink and have us truncate a file of theirs choosing.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        return runtime
    fallback = os.path.join(os.path.expanduser("~"), ".cache", "entropy-shield")
    os.makedirs(fallback, mode=0o700, exist_ok=True)
    return fallback


def _acquire_lock() -> bool:
    """Return True if this is the first instance, False if one is already running."""
    global _instance_lock
    if os.name == "nt":
        from core.windows.singleton import acquire
        return acquire("gui")
    import fcntl
    lock_path = os.path.join(_lock_dir(), "entropy-shield.lock")
    try:
        fd = os.open(lock_path,
                     os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        _instance_lock = os.fdopen(fd, "w")
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main() -> None:
    # The frozen Windows build starts the elevated helper from the same EXE.
    if os.name == "nt" and ("--windows-helper" in sys.argv
                            or "--windows-helper-persist" in sys.argv):
        if "--windows-helper-persist" in sys.argv:
            os.environ["ENTROPY_SHIELD_HELPER_PERSIST"] = "1"
        from core.windows.daemon_win import main as helper_main
        sys.exit(helper_main())

    # Maintenance mode used by restore-windows.ps1 / uninstall-windows.ps1.
    # It must run before the single-instance lock so recovery still works while
    # the GUI is open (and on machines without Python, via the frozen EXE).
    if os.name == "nt" and "--windows-restore" in sys.argv:
        from core.windows.restore import main as restore_main
        sys.exit(restore_main())

    if not _acquire_lock():
        print("Entropy Shield is already running.")
        sys.exit(0)

    # Headless / systemd service mode: run the privileged daemon directly.
    # This must be invoked as root (systemd does this); it no longer shells out
    # to sudo/pkexec.  The desktop GUI talks to this daemon over its socket.
    if "--service" in sys.argv or "--headless" in sys.argv:
        if os.name == "nt":
            print("Windows uses the on-demand UAC helper; --service is not supported.")
            sys.exit(1)
        if os.geteuid() != 0:
            print("ERROR: headless/service mode must run as root.\n"
                  "Use the systemd service instead:\n"
                  "    sudo systemctl enable --now entropy-shield")
            sys.exit(1)
        from core.daemon import main as daemon_main
        daemon_main()
        return

    # Only force QT_QPA_PLATFORM when neither Wayland nor X11 is set in env.
    if os.name != "nt" and not os.environ.get("QT_QPA_PLATFORM"):
        if os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        elif os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFontDatabase
    from gui.main_window import MainWindow

    # Start hidden in the system tray only (no visible window). Used by the
    # autostart entry so the app comes up in the tray on login without popping
    # the GUI open. The user can restore the window from the tray menu.
    start_hidden = "--tray" in sys.argv or "--minimized" in sys.argv

    app = QApplication(sys.argv)
    # Fusion draws the same on every desktop.  Platform styles (KDE Breeze in
    # particular) paint their own blue focus frame around buttons that ignores
    # the stylesheet and does not follow the button's shape.
    app.setStyle("Fusion")
    app.setApplicationName("Entropy Shield")
    # Keep running in the tray even when the main window is hidden/closed.
    app.setQuitOnLastWindowClosed(False)

    # Register every bundled font.  The non-commercial Pixeled font is never
    # shipped in the public repository; when it is absent, the Pixel theme
    # falls back to the OFL-licensed Press Start 2P next to it.
    _font_dir = os.path.join(os.path.dirname(__file__), "Fonts")
    if os.path.isdir(_font_dir):
        for _font_name in sorted(os.listdir(_font_dir)):
            if _font_name.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(
                    os.path.join(_font_dir, _font_name))

    w = MainWindow()
    if not start_hidden:
        w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
