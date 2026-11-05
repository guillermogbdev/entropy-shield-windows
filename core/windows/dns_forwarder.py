"""A tiny DNS relay bound to 127.0.0.1:53 (and ::1:53).

Windows' DNS client can only be pointed at an address, not a port.  Tor's
DNSPort and dnscrypt-proxy listen on configurable high ports, so this relay
bridges the gap: the system resolver talks to port 53 here, and every query is
handed to whichever privacy DNS service is active.

It also has a practical benefit: the relay routes both UDP and TCP, and can
fall back from one to the other when Tor's DNSPort is configured for TCP.
"""
from __future__ import annotations

import socket
import socketserver
import struct
import threading
from typing import Callable

_LISTEN_PORT = 53
_TIMEOUT = 10.0


def _servfail(query: bytes) -> bytes:
    """Build a minimal SERVFAIL reply from *query* (best effort)."""
    if len(query) < 12:
        return b""
    tid = query[:2]
    flags = b"\x81\x82"  # QR=1, RD=1, RA=1, RCODE=2
    qdcount = query[4:6]
    # Echo the question section when it is present and well-formed.
    question = b""
    try:
        off = 12
        labels = 0
        while off < len(query) and labels < 128:
            ln = query[off]
            if ln == 0:
                off += 1
                break
            off += 1 + ln
            labels += 1
        if off + 4 <= len(query):
            question = query[12:off + 4]
    except Exception:
        question = b""
    return tid + flags + qdcount + b"\x00\x00\x00\x00\x00\x00" + question


class _UDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        upstream = self.server.upstream_port  # type: ignore[attr-defined]
        reply = b""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.settimeout(_TIMEOUT)
                u.sendto(data, ("127.0.0.1", upstream))
                reply, _ = u.recvfrom(65535)
        except OSError:
            # Some upstreams are TCP-only (for example when forced through a
            # SOCKS proxy); retry over TCP before giving up.
            try:
                reply = _tcp_exchange(data, upstream)
            except OSError:
                reply = b""
        if not reply:
            reply = _servfail(data)
        if reply:
            try:
                sock.sendto(reply, self.client_address)
            except OSError:
                pass


class _TCPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = self.server.upstream_port  # type: ignore[attr-defined]
        sock: socket.socket = self.request
        try:
            sock.settimeout(_TIMEOUT)
            head = _recv_exact(sock, 2)
            if len(head) != 2:
                return
            length = struct.unpack("!H", head)[0]
            query = _recv_exact(sock, length)
            if len(query) != length:
                return
            reply = _tcp_exchange(query, upstream)
            if reply:
                sock.sendall(struct.pack("!H", len(reply)) + reply)
        except OSError:
            pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _tcp_exchange(query: bytes, upstream_port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", upstream_port), timeout=_TIMEOUT) as s:
        s.settimeout(_TIMEOUT)
        s.sendall(struct.pack("!H", len(query)) + query)
        head = _recv_exact(s, 2)
        if len(head) != 2:
            return b""
        length = struct.unpack("!H", head)[0]
        return _recv_exact(s, length)


class _UDP6Server(socketserver.ThreadingUDPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True


class _TCP6Server(socketserver.ThreadingTCPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True


class _UDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True


class _TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class DnsForwarder:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._servers: list[socketserver.BaseServer] = []
        self._threads: list[threading.Thread] = []
        self._upstream = 0
        self.running = False

    def start(self, upstream_port: int, port: int = _LISTEN_PORT) -> bool:
        self.stop()
        self._upstream = int(upstream_port)
        try:
            v4_udp = _UDPServer(("127.0.0.1", port), _UDPHandler)
            v4_tcp = _TCPServer(("127.0.0.1", port), _TCPHandler)
        except OSError as exc:
            self._log(f"[DNS] Cannot listen on 127.0.0.1:{port}: {exc}")
            return False
        pairs: list[tuple[socketserver.BaseServer, str]] = [
            (v4_udp, f"udp4:{port}"), (v4_tcp, f"tcp4:{port}")
        ]
        for cls, label in ((_UDP6Server, "udp6"), (_TCP6Server, "tcp6")):
            try:
                srv = cls(("::1", port), _UDPHandler if "udp" in label else _TCPHandler)
                pairs.append((srv, f"{label}:{port}"))
            except OSError:
                pass

        for srv, label in pairs:
            srv.upstream_port = self._upstream  # type: ignore[attr-defined]
            srv.daemon_threads = True
            srv.allow_reuse_address = True
            t = threading.Thread(target=srv.serve_forever, name=f"dns-{label}", daemon=True)
            t.start()
            self._servers.append(srv)
            self._threads.append(t)
        self.running = True
        self._log(f"[DNS] Local forwarder 127.0.0.1:{port} → 127.0.0.1:{self._upstream}.")
        return True

    def stop(self) -> None:
        for srv in self._servers:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        self._servers.clear()
        for t in self._threads:
            try:
                t.join(timeout=2)
            except Exception:
                pass
        self._threads.clear()
        self.running = False
