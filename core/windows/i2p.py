"""i2pd management for Windows (HTTP/SOCKS proxy mode).

Transparent I2P routing relies on redsocks + iptables on Linux.  Windows has
neither, so this backend exposes i2pd's HTTP and SOCKS proxies and the browser
buttons create isolated profiles pointed at them.
"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Callable

from core.config import cfg, cfg_port

from . import paths


class WindowsI2PManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._proc: subprocess.Popen | None = None
        self._bin: str | None = None
        self._conf = paths.data_dir() / "i2pd.conf"
        self._data = paths.data_dir() / "i2pd-data"
        self._transparent = False

    @property
    def transparent(self) -> bool:
        return False

    def is_installed(self) -> bool:
        if self._bin is None:
            self._bin = paths.find_binary("i2pd.exe", "i2pd")
        return self._bin is not None

    def configure(self, use_tor: bool = False) -> None:
        if not self.is_installed() or not self._bin:
            raise RuntimeError(
                "i2pd.exe was not found. Run scripts/setup-windows.ps1 or put "
                "it in bin\\i2pd."
            )
        paths.ensure_dirs()
        self._data.mkdir(parents=True, exist_ok=True)
        http_port = cfg_port("i2p", "http_port")
        socks_port = cfg_port("i2p", "socks_port")
        bw = cfg().get("i2p", "max_bandwidth")
        bw = bw if isinstance(bw, int) and not isinstance(bw, bool) else 0

        if use_tor:
            via_tor = bool(cfg().get("i2p", "via_tor"))
        else:
            via_tor = False
        lines = [
            "# entropy-shield — auto-generated Windows i2pd.conf",
            "# i2pd uses top-level keys for logging and bandwidth; [log]",
            "# is not a section in this build.",
            "log = file",
            f"logfile = {str(paths.data_dir() / 'i2pd.log').replace(chr(92), '/')}",
            "loglevel = warn",
            "",
            "[httpproxy]",
            "enabled = true",
            "address = 127.0.0.1",
            f"port = {http_port}",
            "",
            "[socksproxy]",
            "enabled = true",
            "address = 127.0.0.1",
            f"port = {socks_port}",
            "",
            "[ssu2]",
            # SSU2 is UDP and Tor cannot carry it; keep it off when tunnelling
            # I2P through Tor.  Direct I2P keeps SSU2 enabled (its UDP is in
            # ProxyBridge's DIRECT list).
            f"enabled = {'false' if via_tor else 'true'}",
        ]
        if via_tor:
            lines += [
                "",
                "[ntcp2]",
                f"proxy = socks://127.0.0.1:{cfg_port('tor', 'socks_port')}",
            ]
        if bw > 0:
            lines += ["", f"bandwidth = {bw}"]
        lines.append("")
        self._conf.write_text("\n".join(lines), encoding="utf-8")
        self._log(
            f"[I2P] Configured HTTP proxy 127.0.0.1:{http_port}, "
            f"SOCKS 127.0.0.1:{socks_port}"
            + (" (NTCP2 via Tor SOCKS)" if via_tor else " (direct transport)")
        )

    def start(self, transparent: bool = False) -> None:
        if not self._bin:
            raise RuntimeError("i2pd.exe was not found.")
        self._log("[I2P] Starting i2pd…")
        self._proc = paths.popen(
            [self._bin, f"--conf={self._conf}", f"--datadir={self._data}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 30
        port = cfg_port("i2p", "http_port")
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError("i2pd exited during startup.")
            if self._port_open(port):
                self._transparent = False
                self._log("[I2P] i2pd active (proxy mode).")
                return
            time.sleep(0.5)
        self.stop()
        raise RuntimeError(f"i2pd did not open 127.0.0.1:{port}.")

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        except Exception:
            pass
        self._log("[I2P] i2pd stopped.")
