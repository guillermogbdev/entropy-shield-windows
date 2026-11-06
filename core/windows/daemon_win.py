#!/usr/bin/env python3
"""Elevated helper process for Entropy Shield on Windows.

The GUI starts this once with UAC.  It listens only on 127.0.0.1, requires a
random token from a per-user control file, and performs the privileged
operations: Windows Firewall kill switch, system DNS and the WinINET proxy.
It exits after a period of inactivity, and repairs firewall/DNS/proxy state on
startup if a previous helper was killed.
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import socket
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.windows import netconfig, paths
from core.windows.admin import is_admin
from core.windows.firewall import WindowsFirewallManager
from core.windows.session import ServerState, handle_client, _stop_torify
from core.windows.singleton import acquire

_CONTROL = paths.data_dir() / "daemon.json"
_LOG = paths.data_dir() / "daemon.log"
_PERSIST = os.environ.get("ENTROPY_SHIELD_HELPER_PERSIST") == "1"
_IDLE_EXIT = 0 if _PERSIST else 60 * 60
_MAX_CONTROL = 4096


def _log(msg: str) -> None:
    paths.ensure_dirs()
    try:
        if _LOG.exists() and _LOG.stat().st_size > 2 * 1024 * 1024:
            _LOG.replace(_LOG.with_suffix(".log.1"))
    except OSError:
        pass
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _write_control(port: int, token: str) -> None:
    paths.ensure_dirs()
    data = {
        "pid": os.getpid(),
        "port": int(port),
        "token": token,
        "started": time.time(),
        # The GUI must not stop a helper started by the logon task: keeping it
        # alive is what avoids a UAC prompt on the next Connect.
        "persist": _PERSIST,
    }
    tmp = _CONTROL.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, _CONTROL)


def _remove_control(pid: int) -> None:
    try:
        data = json.loads(_CONTROL.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) == pid:
            _CONTROL.unlink()
    except Exception:
        pass


def _heal() -> None:
    _log("[HEAL] Repairing state from a previous session…")
    try:
        WindowsFirewallManager(_log).heal()
    except Exception as exc:
        _log(f"[HEAL] Firewall: {exc}")
    netconfig.heal(_log)


def _serve() -> int:
    if not is_admin():
        _log("[ERR] The Windows helper must run elevated.")
        return 1
    if not acquire("helper"):
        _log("[HEAL] Another helper is already running; exiting.")
        return 0

    _heal()
    token = secrets.token_urlsafe(32)
    stop = threading.Event()
    state = ServerState(_log, stop)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", 0))
    except OSError as exc:
        _log(f"[ERR] Cannot bind helper socket: {exc}")
        return 1
    srv.listen(4)
    srv.settimeout(2.0)
    port = srv.getsockname()[1]
    _write_control(port, token)
    _log(f"[DAEMON] Listening on 127.0.0.1:{port}"
         + (" (persistent helper)." if _PERSIST else ""))

    def _stop(*_a) -> None:
        stop.set()
        try:
            srv.close()
        except Exception:
            pass

    try:
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    last_client = time.time()
    try:
        while not stop.is_set():
            try:
                conn, _addr = srv.accept()
            except socket.timeout:
                if (_IDLE_EXIT and state.active is None
                        and time.time() - last_client > _IDLE_EXIT):
                    _log("[DAEMON] Idle timeout — exiting.")
                    break
                continue
            except OSError:
                break
            last_client = time.time()
            try:
                conn.settimeout(20)
                head = conn.recv(_MAX_CONTROL)
                line = head.decode(errors="replace").splitlines()[0] if head else ""
                if line != f"AUTH {token}":
                    try:
                        conn.sendall(b"[ERR] authentication failed\n")
                    except OSError:
                        pass
                    conn.close()
                    continue
                conn.settimeout(None)
                try:
                    conn.sendall(b"[AUTH] ok\n")
                except OSError:
                    conn.close()
                    continue
                handle_client(conn, state)
            except Exception as exc:
                _log(f"[DAEMON] client error: {exc}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                last_client = time.time()
    finally:
        _stop_torify(state)
        if state.active is not None:
            try:
                state.active.disconnect()
            except Exception:
                pass
        try:
            # heal() is a no-op unless a snapshot exists, so it cannot disturb
            # a user's own custom DefaultOutboundAction setting.
            WindowsFirewallManager(_log).heal()
        except Exception:
            pass
        try:
            netconfig.heal(_log)
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass
        _remove_control(os.getpid())
        _log("[DAEMON] Stopped.")
    return 0


def main() -> int:
    return _serve()


if __name__ == "__main__":
    raise SystemExit(main())
