"""Network watchdog helpers (no Qt, no privileged code).

A dropped Wi-Fi link can leave the kill switch active while Tor keeps running:
the app still shows PROTECTED but nothing works.  A SOCKS5 handshake against the
local Tor port is a cheap end-to-end check that works in both proxy and
transparent mode, because every configuration reaches Tor on 127.0.0.1.

The function only opens and closes a TCP stream; it does not download anything.
"""
from __future__ import annotations

import socket
import struct

_SOCKS_VERSION = 5
_CMD_CONNECT = 1
_ATYP_DOMAIN = 3
_REPLY_OK = 0


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def socks5_reachable(port: int, host: str, dest_port: int = 443,
                     timeout: float = 5.0) -> bool:
    """Return True when Tor accepts a SOCKS5 CONNECT to *host*:*dest_port*."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)),
                                      timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(bytes([_SOCKS_VERSION, 1, 0]))  # no authentication
            greeting = _recv_exact(sock, 2)
            if greeting != bytes([_SOCKS_VERSION, 0]):
                return False

            name = host.encode("idna")
            if len(name) > 255:
                return False
            request = (bytes([_SOCKS_VERSION, _CMD_CONNECT, 0, _ATYP_DOMAIN,
                              len(name)]) + name
                       + struct.pack("!H", int(dest_port)))
            sock.sendall(request)

            head = _recv_exact(sock, 4)
            if len(head) < 4:
                return False
            if head[0] != _SOCKS_VERSION or head[1] != _REPLY_OK:
                return False
            atyp = head[3]
            if atyp == 1:      # IPv4
                tail = 4 + 2
            elif atyp == 4:    # IPv6
                tail = 16 + 2
            elif atyp == _ATYP_DOMAIN:
                length = _recv_exact(sock, 1)
                if not length:
                    return False
                tail = length[0] + 2
            else:
                return False
            return len(_recv_exact(sock, tail)) == tail
    except (OSError, ValueError):
        return False


def tor_reachable(port: int = 9050, timeout: float = 5.0) -> bool:
    """Return True when Tor can reach the canary host through SOCKS5."""
    return socks5_reachable(port, "check.torproject.org", 443, timeout)
