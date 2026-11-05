"""Transparent system-wide Tor routing on Windows.

Windows has no ``nftables`` equivalent that can redirect every process's
TCP through Tor without a kernel component.  This module drives
`ProxyBridge <https://github.com/InterceptSuite/ProxyBridge>`_ (MIT licensed,
WinDivert based) in headless CLI mode:

* every TCP connection from every process is redirected to Tor's SOCKS port;
* UDP is blocked (Tor cannot carry UDP, and leaving it open would leak DNS,
  QUIC/HTTP3 and WebRTC traffic outside the tunnel);
* an explicit DIRECT list keeps the privacy daemons from looping through the
  tunnel (``tor.exe`` itself, dnscrypt-proxy and i2pd);
* ``per_app_routing`` rules whose identifier looks like a process name are
  translated to ProxyBridge process rules.

WinDivert needs Administrator rights, so the manager fails soft: if the
process cannot start, the connection continues in SOCKS/system-proxy mode and
the user sees a warning in the activity log.  The Windows Firewall kill switch
remains the fail-closed backstop in that case.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from core.config import cfg, cfg_port

from . import paths
from .admin import is_admin

_READY_MARKERS = ("ProxyBridge started", "Local proxy listening on port")

# Processes that must never be forced through the tunnel: Tor would loop, the
# DNS resolver already speaks to Tor itself, and I2P is a separate network that
# needs its own (UDP) transport.
_DIRECT_PROCESSES = (
    "tor.exe",
    "dnscrypt-proxy.exe",
    "i2pd.exe",
    "ProxyBridge_CLI.exe",
    "Entropy Shield.exe",
)

# Mirrors the Linux backend's local-network exclusions: real LAN traffic must
# not be sent through Tor (printers, NAS, local SSH, router admin pages).
# 10.192.0.0/10 is deliberately absent: that is Tor's virtual .onion range.
_LOCAL_HOSTS = (
    "0.0.0.0/8;10.0.0.0/9;10.128.0.0/10;127.0.0.0/8;"
    "169.254.0.0/16;172.16.0.0/12;192.168.0.0/16;"
    "224.0.0.0/4;240.0.0.0/4;"
    "::1;fe80::/10;fc00::/7"
)


def _vpn_hosts() -> str:
    """Explicit VPN endpoints from ``vpn.allow`` (same list as the firewall)."""
    try:
        nets = cfg().get("vpn", "allow")
    except Exception:
        return ""
    if not isinstance(nets, list):
        return ""
    return ";".join(n for n in nets if isinstance(n, str) and n)


class WindowsTransparentManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._proc: subprocess.Popen | None = None
        self._out = None
        self._profile = paths.data_dir() / "proxybridge-profile.json"
        self._log_file = paths.data_dir() / "proxybridge.log"

    # ── capability checks ──────────────────────────────────────────────────
    def installed(self) -> bool:
        return paths.find_proxybridge() is not None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self.is_running() else None

    # ── profile generation ─────────────────────────────────────────────────
    @staticmethod
    def _rule(process: str, protocol: str, action: str,
              hosts: str = "*", ports: str = "*") -> dict:
        return {
            "ProcessName": process,
            "TargetHosts": hosts,
            "TargetPorts": ports,
            "Protocol": protocol,
            "Action": action,
            "IsEnabled": True,
            "LocalhostViaProxy": False,
            "ProxyConfigId": 1,
        }

    def _per_app_rules(self) -> list[dict]:
        """Translate Windows per-app rules into ProxyBridge rules.

        On Linux the identifier is a uid/user; on Windows we accept a process
        name (for example ``firefox.exe``).  Numeric ids and POSIX usernames are
        skipped so a config written on Linux cannot create nonsense rules.
        """
        par = cfg().get("per_app_routing")
        if not par.get("enabled"):
            return []
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in par.get("rules", []):
            if not isinstance(item, dict):
                continue
            who = str(item.get("uid_or_user", "")).strip()
            if not who or who.isdigit():
                continue
            action = item.get("action", "tor")
            if action == "direct":
                tcp, udp = "DIRECT", "DIRECT"
            elif action == "block":
                tcp, udp = "BLOCK", "BLOCK"
            else:  # tor
                tcp, udp = "PROXY", "BLOCK"
            for proto, what in (("TCP", tcp), ("UDP", udp)):
                key = (who.lower(), proto)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self._rule(who, proto, what))
        return out

    def build_profile(self) -> dict:
        socks = cfg_port("tor", "socks_port")
        # Loopback must always work: the DNS relay (127.0.0.1:53 →
        # dnscrypt-proxy:5380) and every local service use loopback UDP.  An
        # explicit rule is required because the global UDP BLOCK rule would
        # otherwise swallow it (LocalhostViaProxy does not apply to BLOCK
        # rules).  Put it first so no per-app rule can break DNS.
        rules: list[dict] = [
            self._rule("*", "UDP", "DIRECT",
                       hosts="127.0.0.1;::1;localhost"),
        ]
        vpn = _vpn_hosts()
        if vpn:
            rules.append(self._rule("*", "TCP", "DIRECT", hosts=vpn))
            rules.append(self._rule("*", "UDP", "DIRECT", hosts=vpn))
        # Windows Firewall re-evaluates WinDivert's re-injected packets as
        # PID 4 ("System"), so they must stay DIRECT or Tor's own relay
        # connections loop back through Tor.  TCP only: Tor is TCP, and
        # leaving System UDP blocked keeps the leak surface small.
        rules.append(self._rule("System", "TCP", "DIRECT"))
        for process in _DIRECT_PROCESSES:
            rules.append(self._rule(process, "TCP", "DIRECT"))
            rules.append(self._rule(process, "UDP", "DIRECT"))
        rules += self._per_app_rules()
        # Real LAN traffic stays direct, like the Linux nftables ruleset.
        rules.append(self._rule("*", "TCP", "DIRECT", hosts=_LOCAL_HOSTS))
        rules.append(self._rule("*", "UDP", "DIRECT", hosts=_LOCAL_HOSTS))
        rules.append(self._rule("*", "TCP", "PROXY"))
        rules.append(self._rule("*", "UDP", "BLOCK"))
        return {
            "Version": "1.0",
            "IsTrafficLoggingEnabled": False,
            "ProxyConfigs": [{
                "Id": 1,
                "Type": "socks5",
                "Host": "127.0.0.1",
                "Port": str(socks),
                "Username": "",
                "Password": "",
            }],
            "ProxyRules": rules,
        }

    # ── lifecycle ──────────────────────────────────────────────────────────
    def _read_log(self) -> str:
        try:
            return self._log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def start(self, profile_path: str | None = None,
              log_file: str | None = None,
              label: str = "all TCP → Tor, UDP blocked") -> bool:
        if profile_path is None and not cfg().get("windows", "transparent_tor"):
            return False
        cli = paths.find_proxybridge()
        if not cli:
            self._log("[TRANSPARENT] ProxyBridge was not found — apps must use "
                      "the SOCKS proxy (run scripts/setup-windows.ps1 to install "
                      "transparent mode).")
            return False
        if not is_admin():
            self._log("[TRANSPARENT] Administrator rights are required for "
                      "WinDivert — transparent mode skipped. The kill switch "
                      "still blocks direct traffic.")
            return False
        if self.is_running():
            return True

        self.stop()
        paths.ensure_dirs()
        if log_file:
            self._log_file = Path(log_file)
        if profile_path is None:
            try:
                self._profile.write_text(
                    json.dumps(self.build_profile(), indent=2), encoding="utf-8")
            except OSError as exc:
                self._log(f"[TRANSPARENT] Cannot write the ProxyBridge profile: {exc}")
                return False
            active_profile = self._profile
        else:
            active_profile = Path(profile_path)
            if not active_profile.is_file():
                self._log(f"[TRANSPARENT] Profile not found: {active_profile}")
                return False
        try:
            self._log_file.unlink()
        except OSError:
            pass

        self._log("[TRANSPARENT] Starting ProxyBridge "
                  f"({label})…")
        try:
            self._out = open(self._log_file, "wb")
            self._proc = paths.popen(
                [cli, "--profile", str(active_profile), "--verbose", "1"],
                stdout=self._out,
                stderr=subprocess.STDOUT,
                cwd=str(Path(cli).parent),
            )
        except OSError as exc:
            self.stop()
            self._log(f"[TRANSPARENT] Could not start ProxyBridge: {exc}")
            return False

        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            if self._proc.poll() is not None:
                break
            text = self._read_log()
            if any(marker in text for marker in _READY_MARKERS):
                ready = True
                break
            time.sleep(0.4)

        if not ready:
            tail = self._read_log()[-800:].strip()
            detail = tail or "no output"
            self.stop()
            self._log(f"[TRANSPARENT] ProxyBridge did not start ({detail}). "
                      "Falling back to SOCKS/system-proxy mode.")
            return False

        self._log(f"[TRANSPARENT] Active: {label}.")
        return True

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        out, self._out = self._out, None
        if out is not None:
            try:
                out.close()
            except Exception:
                pass
        if proc is not None:
            self._log("[TRANSPARENT] Disabled — normal Windows routing restored.")


def build_torify_profile(exe: str, socks_port: int) -> dict:
    """Profile for "Run an app through Tor": only *exe* is sent through Tor.

    Everything else stays DIRECT, so this can run without connecting the whole
    stack.  LAN/VPN/loopback keep working, and the target process's public UDP
    is blocked (Tor cannot carry it).  The app is monitored by the caller: if
    ProxyBridge dies, the app is terminated instead of leaking directly.
    """
    name = Path(exe).name
    rule = WindowsTransparentManager._rule
    rules: list[dict] = [
        rule("*", "UDP", "DIRECT", hosts="127.0.0.1;::1;localhost"),
    ]
    vpn = _vpn_hosts()
    if vpn:
        rules.append(rule("*", "TCP", "DIRECT", hosts=vpn))
        rules.append(rule("*", "UDP", "DIRECT", hosts=vpn))
    for process in _DIRECT_PROCESSES:
        rules.append(rule(process, "TCP", "DIRECT"))
        rules.append(rule(process, "UDP", "DIRECT"))
    rules.append(rule("System", "TCP", "DIRECT"))
    rules.append(rule("*", "TCP", "DIRECT", hosts=_LOCAL_HOSTS))
    rules.append(rule("*", "UDP", "DIRECT", hosts=_LOCAL_HOSTS))
    rules.append(rule(name, "TCP", "PROXY"))
    rules.append(rule(name, "UDP", "BLOCK"))
    rules.append(rule("*", "TCP", "DIRECT"))
    rules.append(rule("*", "UDP", "DIRECT"))
    return {
        "Version": "1.0",
        "IsTrafficLoggingEnabled": False,
        "ProxyConfigs": [{
            "Id": 1,
            "Type": "socks5",
            "Host": "127.0.0.1",
            "Port": str(int(socks_port)),
            "Username": "",
            "Password": "",
        }],
        "ProxyRules": rules,
    }
