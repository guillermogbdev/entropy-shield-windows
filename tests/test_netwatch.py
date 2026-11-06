"""Tests for the SOCKS5 reachability check used by the network watchdog."""
from __future__ import annotations

import socket
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.netwatch import socks5_reachable  # noqa: E402


class _FakeSocks(threading.Thread):
    """Minimal SOCKS5 server that answers CONNECT with a fixed reply code."""

    def __init__(self, reply: int) -> None:
        super().__init__(daemon=True)
        self.reply = reply
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.sock.settimeout(5)
        self.port = self.sock.getsockname()[1]

    def run(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        try:
            conn.settimeout(5)
            conn.recv(3)                       # greeting
            conn.sendall(b"\x05\x00")
            head = conn.recv(4)                # VER CMD RSV ATYP
            if len(head) == 4 and head[3] == 3:
                length = conn.recv(1)[0]
                conn.recv(length + 2)          # host + port
            conn.sendall(bytes([5, self.reply, 0, 1])
                         + b"\x7f\x00\x00\x01" + b"\x00\x50")
        except OSError:
            pass
        finally:
            conn.close()
            self.sock.close()


class NetwatchTest(unittest.TestCase):
    def _with_server(self, reply: int) -> bool:
        server = _FakeSocks(reply)
        server.start()
        try:
            return socks5_reachable(server.port, "example.com", 443, timeout=3)
        finally:
            server.join(timeout=5)

    def test_success_reply_is_reachable(self) -> None:
        self.assertTrue(self._with_server(0))

    def test_refused_reply_is_not_reachable(self) -> None:
        self.assertFalse(self._with_server(5))

    def test_closed_port_is_not_reachable(self) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        self.assertFalse(socks5_reachable(port, "example.com", 443, timeout=1))


if __name__ == "__main__":
    unittest.main()
