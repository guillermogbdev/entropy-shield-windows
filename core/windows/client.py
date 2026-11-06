"""Client side of the elevated helper's loopback protocol."""
from __future__ import annotations

import json
import socket
import threading
import time

from . import paths
from .admin import start_helper

_CONTROL = paths.data_dir() / "daemon.json"
_CONTROL_SIZE = 4096
_lock = threading.Lock()


class HelperError(RuntimeError):
    pass


def _control() -> dict | None:
    try:
        raw = _CONTROL.read_text(encoding="utf-8")[:_CONTROL_SIZE]
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        port = int(data.get("port", 0))
        token = str(data.get("token", ""))
        pid = int(data.get("pid", 0))
    except Exception:
        return None
    if not (1 <= port <= 65535) or not token or pid <= 0:
        return None
    return {"port": port, "token": token, "pid": pid,
            "persist": bool(data.get("persist", False))}


def helper_persistent() -> bool:
    """Return True when the running helper was started by the logon task.

    Persistent helpers are meant to outlive the GUI (the task starts them at
    logon), so quitting the app must leave them running; otherwise the next
    Connect would ask for UAC again.  Helpers started on demand with UAC are
    shut down as before.
    """
    info = _control()
    return bool(info and info.get("persist"))


def _open_existing(timeout: float = 3.0):
    info = _control()
    if info is None:
        return None
    try:
        sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=timeout)
        sock.settimeout(timeout)
        sock.sendall(f"AUTH {info['token']}\n".encode())
        # Use one buffered reader for the auth line AND the subsequent
        # "[RUNNER] started" sentinel, so no bytes are lost by a raw recv().
        reader = sock.makefile("rb")
        reply = reader.readline()
        if not reply.startswith(b"[AUTH] ok"):
            reader.close()
            sock.close()
            return None
        sock.settimeout(None)
        return sock, reader
    except OSError:
        return None


def helper_running() -> bool:
    """Check whether the elevated helper is already available (never starts it)."""
    info = _control()
    if info is None:
        return False
    try:
        sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=1.5)
        sock.settimeout(1.5)
        sock.sendall(f"AUTH {info['token']}\n".encode())
        reader = sock.makefile("rb")
        reply = reader.readline()
        reader.close()
        sock.close()
        return reply.startswith(b"[AUTH] ok")
    except OSError:
        return False


def shutdown_existing(timeout: float = 5.0) -> None:
    """Ask a running helper to exit cleanly (never starts one)."""
    existing = _open_existing()
    if existing is None:
        return
    sock, reader = existing
    try:
        sock.settimeout(timeout)
        reader.readline()  # [RUNNER] started
        sock.sendall(b"shutdown\n")
        while True:
            line = reader.readline()
            if not line or b"Helper shutting down" in line:
                break
    except OSError:
        pass
    finally:
        try:
            reader.close()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


def panic_existing(timeout: float = 30.0) -> bool:
    """Ask an already-running helper to run its emergency disconnect.

    Never starts a helper and never triggers UAC, so Panic still cleans the
    firewall, DNS and proxy when the GUI's session object is gone but the
    logon-task helper is alive.
    """
    existing = _open_existing(timeout=2.0)
    if existing is None:
        return False
    sock, reader = existing
    try:
        sock.settimeout(timeout)
        reader.readline()  # [RUNNER] started
        sock.sendall(b"panic\n")
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = reader.readline()
            if not line:
                return True
            if b"[PANIC] Connection closed." in line:
                return True
        return False
    except OSError:
        return False
    finally:
        try:
            reader.close()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


def control_request(command: str, timeout: float = 45.0,
                    start: bool = True) -> dict:
    """One command/reply over a short helper connection (torify_*).

    With ``start=False`` it only reuses an existing helper and never triggers
    UAC (used from atexit cleanup).  Returns ``{"ok": False, ...}`` instead of
    raising so the caller can fall back to proxy-env mode.
    """
    if start:
        try:
            existing = connect(timeout=timeout)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    else:
        existing = _open_existing(timeout=2.0)
        if existing is None:
            return {"ok": False, "error": "helper is not running"}
    sock, reader = existing
    try:
        reader.readline()  # [RUNNER] started
        sock.settimeout(timeout)
        sock.sendall((command.rstrip("\n") + "\n").encode())
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = reader.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            if text.startswith("[TORIFY] "):
                try:
                    return json.loads(text[len("[TORIFY] "):])
                except Exception:
                    return {"ok": False, "error": text}
        return {"ok": False, "error": "helper did not answer in time"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            reader.close()
            sock.close()
        except Exception:
            pass


def connect(timeout: float = 30.0):
    """Return (socket, buffered reader) to the helper, starting it with UAC."""
    existing = _open_existing()
    if existing is not None:
        return existing

    with _lock:
        existing = _open_existing()
        if existing is not None:
            return existing
        # Leave a stale control file in place: the new helper overwrites it.
        # If an old helper is actually alive but briefly unreachable, keeping
        # its file lets the retry loop reconnect to it instead of failing.
        ok, msg = start_helper()
        if not ok:
            raise HelperError(msg)

        deadline = time.time() + timeout
        while time.time() < deadline:
            existing = _open_existing(timeout=1.5)
            if existing is not None:
                return existing
            time.sleep(0.25)
    raise HelperError(
        "The privileged helper did not start. Windows may have blocked the UAC "
        "prompt, or another security product is preventing the firewall rules.")
