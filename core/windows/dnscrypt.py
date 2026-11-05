"""dnscrypt-proxy management for Windows.

A dedicated configuration is generated in the per-user data directory instead
of modifying a system-wide TOML file.  dnscrypt-proxy can route its upstream
queries through Tor's SOCKS port when Tor is also selected, so DNS is then both
encrypted and anonymised.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable

from core.config import cfg, cfg_port

from . import paths


def _toml_str(value: str) -> str:
    return value.replace("\\", "/").replace("'", "\\'")


class WindowsDNSCryptManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._proc: subprocess.Popen | None = None
        self._bin: str | None = None
        self._conf = paths.data_dir() / "dnscrypt-proxy.toml"
        self._log_file = paths.data_dir() / "dnscrypt-proxy.log"
        self._port = 5380

    def is_installed(self) -> bool:
        if self._bin is None:
            self._bin = paths.find_binary("dnscrypt-proxy.exe", "dnscrypt_proxy")
        return self._bin is not None

    def configure(self, via_tor: bool = False, tor_socks: int = 9050) -> None:
        if not self.is_installed() or not self._bin:
            raise RuntimeError(
                "dnscrypt-proxy.exe was not found. Run "
                "scripts/setup-windows.ps1 or put it in bin\\dnscrypt-proxy."
            )
        paths.ensure_dirs()
        self._port = cfg_port("dnscrypt", "port")
        dnssec = "true" if cfg().get("dnscrypt", "require_dnssec") else "false"
        nolog = "true" if cfg().get("dnscrypt", "require_nolog") else "false"
        nofilter = "true" if cfg().get("dnscrypt", "require_nofilter") else "false"
        proxy_line = ""
        force_tcp = "false"
        netprobe = 60
        if via_tor:
            proxy_line = f"proxy = 'socks5://127.0.0.1:{tor_socks}'\n"
            force_tcp = "true"
            # Do not let the connectivity probe make a direct clearnet
            # connection while every real lookup goes through Tor.
            netprobe = 0

        cache = paths.data_dir() / "public-resolvers.md"
        text = f"""# entropy-shield — auto-generated Windows dnscrypt-proxy.toml
listen_addresses = ['127.0.0.1:{self._port}']
max_clients = 250
ipv4_servers = true
ipv6_servers = false
dnscrypt_servers = true
doh_servers = true
odoh_servers = false
require_dnssec = {dnssec}
require_nolog = {nolog}
require_nofilter = {nofilter}
force_tcp = {force_tcp}
timeout = 5000
keepalive = 30
netprobe_timeout = {netprobe}
netprobe_address = '9.9.9.9:53'
ignore_system_dns = true
log_level = 2
log_file = '{_toml_str(str(self._log_file))}'
use_syslog = false
cache = true
cache_size = 4096
cache_min_ttl = 2400
cache_max_ttl = 86400
cache_neg_min_ttl = 60
cache_neg_max_ttl = 600
{proxy_line}
[sources]
  [sources.public-resolvers]
  urls = ['https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md', 'https://download.dnscrypt.info/resolvers-list/v3/public-resolvers.md']
  cache_file = '{_toml_str(str(cache))}'
  minisign_key = 'RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3'
  refresh_delay = 72
  prefix = ''
"""
        self._conf.write_text(text, encoding="utf-8")
        self._log(f"[DNS] dnscrypt-proxy configured on 127.0.0.1:{self._port}"
                  + (" (upstream via Tor SOCKS)" if via_tor else ""))

    def start(self) -> None:
        if not self._bin:
            raise RuntimeError("dnscrypt-proxy.exe was not found.")
        self._log("[DNS] Starting dnscrypt-proxy…")
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        # -check catches syntax errors before a process is left half-started.
        try:
            chk = paths.run([self._bin, "-check", "-config", str(self._conf)],
                            timeout=20, text=True)
            if chk.returncode != 0:
                out = ((chk.stdout or "") + (chk.stderr or "")).strip()
                raise RuntimeError(f"dnscrypt-proxy config error: {out}")
        except FileNotFoundError:
            raise RuntimeError(f"dnscrypt-proxy.exe not found at {self._bin}")
        except subprocess.TimeoutExpired:
            pass

        self._proc = paths.popen(
            [self._bin, "-config", str(self._conf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    "dnscrypt-proxy exited during startup. "
                    + self._tail_log())
            if self._port_open(self._port):
                self._warmup()
                self._log("[DNS] dnscrypt-proxy active.")
                return
            time.sleep(0.5)
        self.stop()
        raise RuntimeError(
            f"dnscrypt-proxy did not start listening on 127.0.0.1:{self._port}. "
            + self._tail_log())

    def _warmup(self) -> None:
        """Wait until the resolver list is usable.

        dnscrypt-proxy starts listening before it has necessarily downloaded
        and validated its public-resolvers list.  The very first query can then
        time out; sending a few test queries first avoids a cold-start leak-test
        failure.
        """
        try:
            from core.leak_test import _dns_query_udp
        except Exception:
            return
        for _ in range(3):
            try:
                reply = _dns_query_udp(self._port, "example.com")
                if len(reply) > 12 and (reply[3] & 0x0F) == 0:
                    return
            except OSError:
                pass
            except Exception:
                pass
            time.sleep(2)
        self._log("[DNS] Warning: dnscrypt-proxy has not answered a test query "
                  "yet; the first lookup may be slow.")

    def _tail_log(self) -> str:
        try:
            lines = self._log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            return " ".join(l.strip() for l in lines[-4:] if l.strip())
        except OSError:
            return ""

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def pre_restore(self) -> None:
        pass

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        except Exception:
            pass
        self._log("[DNS] dnscrypt-proxy stopped.")

    def nixos_redirect_dns(self) -> None:
        pass

    def nixos_restore_dns(self) -> None:
        pass
