"""Line protocol served by the elevated Windows helper.

The commands and sentinels intentionally match ``core/daemon.py`` so the GUI's
worker threads need no Windows-specific code path.
"""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Callable

from . import paths
from .connection import WindowsConnectionManager
from .firewall import WindowsFirewallManager
from .transparent import WindowsTransparentManager
from core.config import cfg

_ALLOWED = ("use_tor", "use_dnscrypt", "use_i2p", "use_onion_server")
_MAX_LINE = 4096
_session_lock = threading.Lock()


class ServerState:
    def __init__(self, log: Callable[[str], None], stop_event: threading.Event):
        self.log = log
        self.stop_event = stop_event
        self.active: WindowsConnectionManager | None = None
        # Per-app transparent ProxyBridge instance ("Run an app through Tor").
        self.torify: WindowsTransparentManager | None = None


def _stop_torify(state: ServerState) -> None:
    mgr, state.torify = getattr(state, "torify", None), None
    if mgr is not None:
        try:
            mgr.stop()
        except Exception:
            pass


def _force_remove_firewall(log: Callable[[str], None]) -> None:
    try:
        WindowsFirewallManager(log).remove()
    except Exception:
        pass


def handle_client(conn: socket.socket, state: ServerState) -> None:
    rfile = conn.makefile("rb")
    wfile = conn.makefile("wb")
    write_lock = threading.Lock()

    def log(msg: str) -> None:
        with write_lock:
            try:
                wfile.write((msg + "\n").encode())
                wfile.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
        try:
            state.log(msg)
        except Exception:
            pass

    mgr: WindowsConnectionManager | None = None
    connected = False
    try:
        with _session_lock:
            log("[RUNNER] started")
            while not state.stop_event.is_set():
                raw = rfile.readline(_MAX_LINE)
                if not raw:
                    if mgr is not None:
                        try:
                            mgr.disconnect()
                        except Exception:
                            pass
                    return
                cmd = raw.decode(errors="replace").strip()
                if not cmd:
                    continue

                if cmd == "ping":
                    log("[OK] pong")

                elif cmd.startswith("connect "):
                    if mgr is not None:
                        log("[ERR] A session is already active on this connection.")
                        continue
                    try:
                        params = json.loads(cmd[8:])
                        if not isinstance(params, dict):
                            raise ValueError("connect payload must be a JSON object")
                        safe = {k: bool(params.get(k, False)) for k in _ALLOWED}
                        # The helper outlives the GUI's settings panel, so a
                        # newly saved per-app rule or toggle would otherwise be
                        # invisible until the helper process restarted.
                        cfg().reload()
                        mgr = WindowsConnectionManager(log)
                        state.active = mgr
                        mgr.connect(**safe)
                        connected = True
                    except Exception as exc:
                        log(f"[ERR] {exc}")

                elif cmd == "disconnect":
                    if mgr is not None:
                        try:
                            mgr.disconnect()
                        except Exception as exc:
                            log(f"[ERR] {exc}")
                    state.active = None
                    connected = False
                    return

                elif cmd.startswith("torify_start "):
                    try:
                        params = json.loads(cmd[len("torify_start "):])
                        if not isinstance(params, dict):
                            raise ValueError("payload must be a JSON object")
                        profile = Path(str(params.get("profile", ""))).resolve()
                        base = paths.data_dir().resolve()
                        if base != profile.parent and base not in profile.parents:
                            raise ValueError("profile must live under the data directory")
                        if not profile.is_file():
                            raise ValueError("profile not found")
                        label = str(params.get("label", "per-app TCP → Tor"))
                        _stop_torify(state)
                        mgr_t = WindowsTransparentManager(log)
                        ok = mgr_t.start(
                            profile_path=str(profile),
                            log_file=str(paths.data_dir() / "torify-pb.log"),
                            label=label,
                        )
                        if ok:
                            state.torify = mgr_t
                            log("[TORIFY] " + json.dumps(
                                {"ok": True, "pid": mgr_t.pid}))
                        else:
                            log("[TORIFY] " + json.dumps(
                                {"ok": False,
                                 "error": "ProxyBridge did not start"}))
                    except Exception as exc:
                        log("[TORIFY] " + json.dumps(
                            {"ok": False, "error": str(exc)}))

                elif cmd == "torify_stop":
                    _stop_torify(state)
                    log('[TORIFY] {"ok": true}')

                elif cmd == "torify_status":
                    running = bool(state.torify and state.torify.is_running())
                    pid = state.torify.pid if state.torify else None
                    log("[TORIFY] " + json.dumps(
                        {"ok": True, "running": running, "pid": pid}))

                elif cmd == "new_circuit":
                    if mgr is None or not connected:
                        log("[ERR] Tor is not connected.")
                        continue
                    try:
                        mgr._tor.new_circuit()
                        log("[TOR] New Tor circuit requested.")
                    except Exception as exc:
                        log(f"[ERR] Circuit renewal failed: {exc}")

                elif cmd == "circuit_info":
                    if mgr is None or not connected:
                        log("[CIRCUIT] {}")
                        continue
                    try:
                        log("[CIRCUIT] " + json.dumps(mgr._tor.get_circuit_info()))
                    except Exception:
                        log("[CIRCUIT] {}")

                elif cmd == "status":
                    log("[STATUS] " + json.dumps({
                        "connected": connected,
                        "layers": getattr(mgr, "_layers", {}) if mgr else {},
                    }))

                elif cmd == "panic":
                    log("[PANIC] Emergency disconnect…")
                    _stop_torify(state)
                    if mgr is not None:
                        try:
                            mgr.disconnect()
                        except Exception as exc:
                            log(f"[PANIC] Disconnect error: {exc}")
                            _force_remove_firewall(log)
                    else:
                        _force_remove_firewall(log)
                    state.active = None
                    log("[PANIC] Connection closed.")
                    return

                elif cmd == "shutdown":
                    _stop_torify(state)
                    if mgr is not None:
                        try:
                            mgr.disconnect()
                        except Exception:
                            pass
                    state.active = None
                    log("[OK] Helper shutting down.")
                    state.stop_event.set()
                    return

                else:
                    log("[ERR] unknown command")
    finally:
        state.active = None
        for f in (wfile, rfile):
            try:
                f.close()
            except Exception:
                pass
