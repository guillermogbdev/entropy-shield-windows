"""Liveness checks for the Windows services."""
from __future__ import annotations

import socket
import subprocess
import time
from typing import Iterable

from core.config import cfg_port

from .paths import no_window_flags


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def process_running(image: str) -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True, text=True, timeout=4,
            creationflags=no_window_flags(),
        )
        return image.lower() in (r.stdout or "").lower()
    except Exception:
        return False


def check_layers(active_layers: Iterable[str]) -> tuple[str, str] | None:
    """Return (service, detail) for the first layer that looks dead."""
    layers = set(active_layers)
    if "tor" in layers:
        port = cfg_port("tor", "socks_port")
        if not port_open(port):
            time.sleep(3)
            if not port_open(port):
                return ("tor", f"Tor SocksPort :{port} is unreachable.")
    if "dnscrypt" in layers:
        port = cfg_port("dnscrypt", "port")
        if not (process_running("dnscrypt-proxy.exe") or port_open(port)):
            return ("dnscrypt-proxy", "dnscrypt-proxy is not running.")
    if "i2p" in layers:
        port = cfg_port("i2p", "http_port")
        if not (process_running("i2pd.exe") or port_open(port)):
            return ("i2pd", "i2pd is not running.")
    if "onion_server" in layers:
        port = cfg_port("onion_server", "local_port")
        if not port_open(port):
            return ("onion server", f"Local HTTP server :{port} is unreachable.")
    return None
