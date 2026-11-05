"""Tor management for Windows.

Windows has no ``TransPort`` (transparent proxy) support and no nftables, so
Tor is run as a local SOCKS/HTTP proxy.  The GUI points the system WinINET
proxy at the SocksPort and isolates browser profiles explicitly; the kill
switch makes sure applications that ignore the proxy cannot reach the network.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from core.config import cfg, cfg_port

from . import paths

_FATAL = (
    "[err]", "problem bootstrapping", "failed to bind",
    "address already in use", "could not bind", "another tor process",
    "unable to open", "permission denied",
)


def _posix(path: Path | str) -> str:
    """Tor accepts forward slashes on Windows; they avoid escape sequences."""
    return str(path).replace("\\", "/")


class WindowsTorManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._proc: subprocess.Popen | None = None
        self._bootstrap_done: threading.Event | None = None
        self._bootstrap_error = ""
        self._torrc = paths.data_dir() / "torrc"
        self._data = paths.data_dir() / "tor-data"
        self._bin: str | None = None

    # ── paths / state ───────────────────────────────────────────────────────
    @property
    def torrc_path(self) -> str:
        return str(self._torrc)

    @property
    def data_dir(self) -> Path:
        return self._data

    def binary(self) -> str | None:
        if self._bin is None:
            self._bin = paths.find_binary("tor.exe", "tor")
        return self._bin

    def is_installed(self) -> bool:
        return self.binary() is not None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── configuration ───────────────────────────────────────────────────────
    def configure(self) -> None:
        tor = self.binary()
        if not tor:
            raise RuntimeError(
                "tor.exe was not found. Run scripts/setup-windows.ps1, install "
                "Tor Browser, or put tor.exe in the app's bin\\tor folder."
            )
        self._log("[TOR] Writing Windows torrc…")
        paths.ensure_dirs()
        self._data.mkdir(parents=True, exist_ok=True)

        dns = cfg_port("tor", "dns_port")
        socks = cfg_port("tor", "socks_port")
        ctrl = cfg_port("tor", "control_port")
        exits = str(cfg().get("tor", "exit_nodes")).strip()
        strict = bool(cfg().get("tor", "strict_nodes"))

        tor_dir = Path(tor).parent
        geoip = geoip6 = None
        for base in (tor_dir, tor_dir.parent):
            candidate = base / "data" / "geoip"
            candidate6 = base / "data" / "geoip6"
            if candidate.is_file():
                geoip, geoip6 = candidate, candidate6
                break
        geo_lines = ""
        if geoip is not None:
            geo_lines += f'GeoIPFile "{_posix(geoip)}"\n'
        if geoip6 is not None and geoip6.is_file():
            geo_lines += f'GeoIPv6File "{_posix(geoip6)}"\n'

        lines = [
            "# entropy-shield — auto-generated Windows torrc, do not edit",
            f'DataDirectory "{_posix(self._data)}"',
            "Log notice stderr",
            "",
            "VirtualAddrNetworkIPv4 10.192.0.0/10",
            "AutomapHostsOnResolve 1",
            "AutomapHostsSuffixes .onion,.exit",
            "",
            # Windows has no transparent redirect; TransPort is deliberately
            # omitted because the Windows Tor build rejects it.
            f"DNSPort 127.0.0.1:{dns}",
            f"SocksPort 127.0.0.1:{socks} IsolateDestAddr IsolateDestPort",
            f"ControlPort 127.0.0.1:{ctrl}",
            "CookieAuthentication 1",
            f'CookieAuthFile "{_posix(self._data / "control_auth_cookie")}"',
        ]
        if geo_lines:
            lines.append(geo_lines.rstrip("\n"))
        if exits:
            lines.append(f"ExitNodes {exits}")
        if strict:
            lines.append("StrictNodes 1")
        bridge = self._bridge_section(tor)
        if bridge:
            lines.append(bridge)
        lines.append("")

        self._torrc.write_text("\n".join(lines), encoding="utf-8")
        self._log(f"[TOR] Windows torrc → {self._torrc}")

    def _bridge_section(self, tor: str) -> str:
        br = cfg().get("bridges")
        if not br.get("enabled"):
            return ""
        transport = br.get("transport", "obfs4")
        raw_lines = br.get("lines", [])
        out = ["UseBridges 1"]
        if transport == "obfs4":
            proxy = paths.find_obfs4proxy(tor)
            if not proxy:
                self._log(
                    "[TOR] Bridges need obfs4proxy.exe, which was not found. "
                    "Install the Tor Browser bundle or put obfs4proxy.exe in bin\\tor. "
                    "Starting Tor without bridges.")
                return ""
            out.append(f'ClientTransportPlugin obfs4 exec "{_posix(proxy)}"')
        elif transport == "meek-azure":
            meek = paths.find_meek_client(tor)
            if not meek:
                self._log(
                    "[TOR] meek-azure needs meek-client.exe, which was not found. "
                    "Starting Tor without bridges.")
                return ""
            out.append(f'ClientTransportPlugin meek_lite exec "{_posix(meek)}"')
        # "manual" uses plain Bridge lines; no pluggable transport is needed.
        for item in raw_lines:
            if not isinstance(item, str):
                continue
            line = item.replace("\r", " ").replace("\n", " ").strip()
            if not line or line.startswith("#"):
                continue
            first, _, rest = line.partition(" ")
            if first.lower() == "bridge":
                line = rest.strip()
            if line:
                out.append("Bridge " + line)
        if not raw_lines:
            self._log("[TOR] Bridges are enabled but no bridge lines are configured.")
        return "\n".join(out) if len(out) > 1 else ""

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self) -> None:
        tor = self.binary()
        if not tor:
            raise RuntimeError("tor.exe was not found.")
        self._log(f"[TOR] Starting Tor… ({tor})")

        try:
            chk = paths.run([tor, "--verify-config", "-f", str(self._torrc)],
                            timeout=20, text=True)
            output = ((chk.stdout or "") + (chk.stderr or "")).strip()
            if output:
                for line in output.splitlines()[-8:]:
                    if line.strip():
                        self._log(f"[TOR] {line.strip()}")
            if chk.returncode != 0:
                raise RuntimeError(
                    f"Tor config error (exit {chk.returncode}): "
                    f"{output or 'verify-config failed'}")
        except FileNotFoundError:
            raise RuntimeError(f"tor.exe not found at '{tor}'.")
        except subprocess.TimeoutExpired:
            pass

        self._check_ports()

        self._bootstrap_done = threading.Event()
        self._bootstrap_error = ""
        self._proc = paths.popen(
            [tor, "-f", str(self._torrc)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._stderr_reader, name="tor-stderr", daemon=True).start()

        if not self._bootstrap_done.wait(timeout=120):
            self._terminate()
            raise RuntimeError("Tor bootstrap timed out (120 s). Check your network.")
        if self._bootstrap_error:
            err = self._bootstrap_error
            self._terminate()
            raise RuntimeError(f"Tor failed to start: {err}")
        self._log("[TOR] Tor is running.")

    def stop(self) -> None:
        was_running = self._proc is not None
        if was_running:
            self._log("[TOR] Stopping Tor…")
            self._terminate()
        # Remove the generated torrc even when configure() succeeded but the
        # process never started (a later layer failed and rolled back).
        try:
            self._torrc.unlink()
        except OSError:
            pass
        if was_running:
            self._log("[TOR] Tor stopped.")

    def _terminate(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception:
            pass

    def _stderr_reader(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        bootstrap_re = re.compile(r"Bootstrapped (\d+)%")
        last_pct = -1
        recent: list[str] = []
        try:
            for raw in proc.stderr:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                recent.append(line)
                if len(recent) > 40:
                    recent.pop(0)
                low = line.lower()
                if any(p in low for p in _FATAL):
                    self._bootstrap_error = line
                    self._log(f"[TOR] {line}")
                m = bootstrap_re.search(line)
                if m:
                    pct = int(m.group(1))
                    if pct != last_pct:
                        last_pct = pct
                        self._log(f"[TOR] Bootstrap: {pct}%")
                    if pct >= 100 and self._bootstrap_done is not None:
                        self._log("[TOR] Bootstrap complete.")
                        self._bootstrap_done.set()
        except Exception:
            pass
        if self._bootstrap_done is not None and not self._bootstrap_done.is_set():
            for line in recent[-8:]:
                self._log(f"[TOR] {line}")
            self._bootstrap_error = self._bootstrap_error or "Tor process ended unexpectedly."
            self._bootstrap_done.set()

    def _check_ports(self) -> None:
        checks = [
            ("SOCKS", "tcp", cfg_port("tor", "socks_port")),
            ("Control", "tcp", cfg_port("tor", "control_port")),
            ("DNS", "udp", cfg_port("tor", "dns_port")),
        ]
        for name, proto, port in checks:
            try:
                if proto == "tcp":
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(("127.0.0.1", port))
                else:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        s.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Port {port} ({name}) is already in use: {exc}") from exc

    # ── control port ────────────────────────────────────────────────────────
    def _cookie_hex(self) -> str:
        with open(self._data / "control_auth_cookie", "rb") as f:
            return f.read().hex()

    def new_circuit(self) -> None:
        ctrl = cfg_port("tor", "control_port")
        cookie = self._cookie_hex()
        with socket.socket() as s:
            s.settimeout(5)
            s.connect(("127.0.0.1", ctrl))
            s.sendall(f"AUTHENTICATE {cookie}\r\n".encode())
            resp = s.recv(1024).decode(errors="replace")
            if not resp.startswith("250"):
                raise RuntimeError(f"Control auth failed: {resp.strip()}")
            s.sendall(b"SIGNAL NEWNYM\r\n")
            resp = s.recv(1024).decode(errors="replace")
            if not resp.startswith("250"):
                raise RuntimeError(f"NEWNYM failed: {resp.strip()}")

    @staticmethod
    def _ctrl_recv(s: socket.socket) -> str:
        resp = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
            decoded = resp.decode(errors="replace")
            if "250 OK" in decoded:
                break
            for ec in ("513 ", "515 ", "552 ", "554 "):
                if f"\n{ec}" in decoded or decoded.startswith(ec):
                    return ""
        text = resp.decode(errors="replace")
        data: list[str] = []
        in_block = False
        for line in text.splitlines():
            if line.startswith("250+") and "=" in line:
                in_block = True
                val = line[4:].partition("=")[2]
                if val:
                    data.append(val)
            elif line == ".":
                in_block = False
            elif in_block and not line.startswith("250"):
                data.append(line)
            elif (line.startswith("250-") or line.startswith("250 ")) and "=" in line:
                data.append(line[4:].partition("=")[2].strip())
        return "\n".join(data)

    def _ctrl_getinfo(self, s: socket.socket, key: str) -> str:
        s.sendall(f"GETINFO {key}\r\n".encode())
        return self._ctrl_recv(s)

    def query_control(self, *commands: str) -> dict[str, str]:
        ctrl = cfg_port("tor", "control_port")
        result: dict[str, str] = {}
        try:
            cookie = self._cookie_hex()
            with socket.socket() as s:
                s.settimeout(4)
                s.connect(("127.0.0.1", ctrl))
                s.sendall(f"AUTHENTICATE {cookie}\r\n".encode())
                s.recv(1024)
                for cmd in commands:
                    value = self._ctrl_getinfo(s, cmd)
                    result[cmd] = value
        except Exception:
            pass
        return result

    def get_circuit_info(self) -> dict:
        ctrl = cfg_port("tor", "control_port")
        empty = {"circuit_count": 0, "exit_country": "",
                 "bytes_read": 0, "bytes_written": 0}
        try:
            cookie = self._cookie_hex()
        except OSError:
            return empty
        try:
            with socket.socket() as s:
                s.settimeout(5)
                s.connect(("127.0.0.1", ctrl))
                s.sendall(f"AUTHENTICATE {cookie}\r\n".encode())
                self._ctrl_recv(s)
                raw = self._ctrl_getinfo(s, "circuit-status")
                built = [l for l in raw.splitlines() if "BUILT" in l]
                general = [l for l in built if "PURPOSE=GENERAL" in l]
                exit_country = ""
                for circ in general:
                    parts = circ.split()
                    if len(parts) < 3 or not parts[2].startswith("$"):
                        continue
                    fp_m = re.match(r"\$([0-9A-Fa-f]{40})", parts[2].split(",")[-1])
                    if not fp_m:
                        continue
                    ns = self._ctrl_getinfo(s, f"ns/id/{fp_m.group(1)}")
                    ip = ""
                    for line in ns.splitlines():
                        if line.startswith("r "):
                            bits = line.split()
                            if len(bits) >= 7:
                                ip = bits[6]
                            break
                    if ip:
                        cc = self._ctrl_getinfo(s, f"ip-to-country/{ip}").strip()
                        if len(cc) == 2 and cc.isalpha() and cc != "ZZ":
                            exit_country = cc.upper()
                    break
                read = self._ctrl_getinfo(s, "traffic/read").strip()
                written = self._ctrl_getinfo(s, "traffic/written").strip()
                return {
                    "circuit_count": len(built),
                    "exit_country": exit_country,
                    "bytes_read": int(read or 0),
                    "bytes_written": int(written or 0),
                }
        except Exception:
            return empty

    # Kept for the connection manager's platform-neutral calls.
    def nixos_redirect_dns(self) -> None:
        pass

    def nixos_restore_dns(self) -> None:
        pass
