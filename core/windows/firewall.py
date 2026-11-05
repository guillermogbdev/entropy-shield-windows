"""Kill switch using Windows Defender Firewall.

Windows evaluates the profile's *default outbound action* before per-program
rules, so the reliable equivalent of the Linux nftables kill switch is:

1. save the current default outbound action for every profile;
2. add Allow rules for Tor / dnscrypt-proxy / i2pd / pluggable transports;
3. switch the default outbound action to Block.

Loopback traffic is exempt, so applications can still reach the local SOCKS,
HTTP and DNS proxies.  Everything that tries to go directly to the internet is
dropped.  The snapshot is written to disk first, and the next helper startup
restores it if the process was killed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import paths
from .admin import is_admin

_GROUP = "Entropy Shield"
_BACKUP = paths.data_dir() / "firewall-backup.json"
_PS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]


def _q(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class WindowsFirewallManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._applied = False
        self._allow_paths: list[str] = []
        self._transparent = False

    # ── PowerShell plumbing ────────────────────────────────────────────────
    @staticmethod
    def _ps(script: str, timeout: float = 40) -> tuple[int, str]:
        try:
            r = subprocess.run(
                [*_PS, "$ErrorActionPreference='Stop'; " + script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=paths.no_window_flags(),
            )
            return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
        except Exception as exc:
            return 1, str(exc)

    def _snapshot(self) -> dict | None:
        if _BACKUP.exists():
            try:
                data = json.loads(_BACKUP.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("profiles") is not None:
                    return data
            except Exception:
                pass
        script = (
            "$p = Get-NetFirewallProfile | Select-Object "
            "@{Name='Name';Expression={$_.Name}},"
            "@{Name='DefaultOutboundAction';Expression={[string]$_.DefaultOutboundAction}}; "
            "$p | ConvertTo-Json -Compress"
        )
        rc, out = self._ps(script)
        if rc != 0:
            self._log(f"[FW] Cannot read firewall profiles: {out}")
            return None
        try:
            parsed = json.loads(out)
        except Exception:
            self._log(f"[FW] Cannot parse firewall profiles: {out[:200]}")
            return None
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list) or not parsed:
            self._log("[FW] Windows Firewall returned no profiles.")
            return None
        data = {"profiles": parsed, "allowed": list(self._allow_paths)}
        paths.ensure_dirs()
        tmp = _BACKUP.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, _BACKUP)
        return data

    # ── rules ──────────────────────────────────────────────────────────────
    def _collect_allowed(self) -> list[str]:
        out: list[str] = []
        for name, key in (("tor.exe", "tor"),
                          ("dnscrypt-proxy.exe", "dnscrypt_proxy"),
                          ("i2pd.exe", "i2pd")):
            found = paths.find_binary(name, key)
            if found and found not in out:
                out.append(found)
        # ProxyBridge (transparent mode) redirects packets with WinDivert.
        # Allow the CLI itself so a strict local policy cannot break it.
        proxybridge = paths.find_proxybridge()
        if proxybridge and proxybridge not in out:
            out.append(proxybridge)
        # Per-app rules that explicitly bypass Tor must also bypass the kill
        # switch, otherwise "direct" would silently mean "blocked".
        try:
            from core.config import cfg
            par = cfg().get("per_app_routing")
            if par.get("enabled"):
                for item in par.get("rules", []):
                    if not isinstance(item, dict) or item.get("action") != "direct":
                        continue
                    who = str(item.get("uid_or_user", "")).strip()
                    if not who or who.isdigit():
                        continue
                    found = shutil.which(who)
                    if found and found not in out:
                        out.append(found)
        except Exception:
            pass
        tor = paths.find_binary("tor.exe", "tor")
        for finder in (paths.find_obfs4proxy, paths.find_meek_client):
            try:
                found = finder(tor)
            except Exception:
                found = None
            if found and found not in out:
                out.append(found)
        return out

    def _remove_rules(self) -> None:
        self._ps(
            f"Get-NetFirewallRule -Group {_q(_GROUP)} -ErrorAction SilentlyContinue "
            "| Remove-NetFirewallRule -ErrorAction SilentlyContinue;"
        )

    def _add_rules(self) -> None:
        parts = ["$ErrorActionPreference='SilentlyContinue';"]
        for path in self._allow_paths:
            name = f"{_GROUP} allow {Path(path).name}"
            parts.append(
                f"New-NetFirewallRule -DisplayName {_q(name)} -Group {_q(_GROUP)} "
                f"-Direction Outbound -Action Allow -Program {_q(path)} "
                "-Profile Any | Out-Null;"
            )
        # DHCP and time sync are infrastructure, not user traffic.  Without
        # DHCP the machine could lose its address after a lease renewal.
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        svchost = str(Path(sysroot) / "System32" / "svchost.exe")
        transparent = self._transparent
        parts += [
            # The GUI and browsers talk to Tor/DNSCrypt over loopback.  Windows
            # normally exempts loopback, but make it explicit so a stricter
            # local policy cannot break the proxies.
            f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' loopback')} -Group {_q(_GROUP)} "
            "-Direction Outbound -Action Allow -RemoteAddress '127.0.0.1','::1' -Profile Any | Out-Null;",
            f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' DHCP')} -Group {_q(_GROUP)} "
            f"-Direction Outbound -Action Allow -Program {_q(svchost)} "
            "-Protocol UDP -LocalPort 68 -RemotePort 67 -Profile Any | Out-Null;",
            f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' time sync')} -Group {_q(_GROUP)} "
            f"-Direction Outbound -Action Allow -Program {_q(svchost)} "
            "-Protocol UDP -RemotePort 123 -Profile Any | Out-Null;",
        ]
        if transparent:
            # WinDivert re-injects proxied-DIRECT packets from the System
            # process (PID 4), so the kill switch must allow them or Tor's own
            # relay connections die.  TCP only; UDP stays blocked.
            parts.append(
                f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' transparent System')} "
                f"-Group {_q(_GROUP)} -Direction Outbound -Action Allow "
                "-Program 'System' -Protocol TCP -Profile Any | Out-Null;"
            )
            # Transparent mode leaves the firewall in allow mode so WinDivert
            # can see every TCP packet.  ProxyBridge blocks UDP, but ICMP/SCTP
            # are outside it; block ICMP explicitly (ping/traceroute leak).
            parts.append(
                f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' ICMPv4')} "
                f"-Group {_q(_GROUP)} -Direction Outbound -Action Block "
                "-Protocol ICMPv4 -Profile Any | Out-Null;"
            )
            parts.append(
                f"New-NetFirewallRule -DisplayName {_q(_GROUP + ' ICMPv6')} "
                f"-Group {_q(_GROUP)} -Direction Outbound -Action Block "
                "-Protocol ICMPv6 -Profile Any | Out-Null;"
            )
        # Explicit VPN endpoints must survive both the kill switch and the
        # transparent UDP block (mirrors Linux's detect_vpn exemption).
        try:
            from core.config import cfg
            vpn_nets = cfg().get("vpn", "allow") or []
        except Exception:
            vpn_nets = []
        for idx, net in enumerate(vpn_nets):
            if not isinstance(net, str) or not net:
                continue
            parts.append(
                f"New-NetFirewallRule -DisplayName {_q(f'{_GROUP} VPN {idx}')} "
                f"-Group {_q(_GROUP)} -Direction Outbound -Action Allow "
                f"-RemoteAddress {_q(net)} -Profile Any | Out-Null;"
            )
        self._ps(" ".join(parts))

    def _block_defaults(self) -> bool:
        rc, out = self._ps(
            "Set-NetFirewallProfile -Profile Domain,Private,Public "
            "-DefaultOutboundAction Block;"
        )
        if rc != 0:
            self._log(f"[FW] Could not block outbound traffic: {out}")
            return False
        return True

    def _restore_defaults(self) -> bool:
        data = None
        try:
            data = json.loads(_BACKUP.read_text(encoding="utf-8"))
        except Exception:
            pass
        profiles = data.get("profiles") if isinstance(data, dict) else None
        if not isinstance(profiles, list):
            profiles = [
                {"Name": "Domain", "DefaultOutboundAction": "Allow"},
                {"Name": "Private", "DefaultOutboundAction": "Allow"},
                {"Name": "Public", "DefaultOutboundAction": "Allow"},
            ]
        parts = ["$ErrorActionPreference='SilentlyContinue';"]
        for item in profiles:
            if not isinstance(item, dict):
                continue
            name = item.get("Name")
            action = item.get("DefaultOutboundAction") or "Allow"
            if name:
                parts.append(
                    f"Set-NetFirewallProfile -Profile {_q(name)} "
                    f"-DefaultOutboundAction {_q(action)};"
                )
        rc, out = self._ps(" ".join(parts))
        if rc != 0:
            self._log(f"[FW] Could not restore the firewall defaults: {out}")
            return False
        return True

    # ── public API ─────────────────────────────────────────────────────────
    def apply(self, use_tor: bool, use_dnscrypt: bool, use_i2p: bool,
              i2p_transparent: bool = False,
              transparent: bool = False) -> bool:
        if not is_admin():
            self._log("[FW] Not elevated — kill switch not enabled.")
            return False
        self._allow_paths = self._collect_allowed()
        if not self._allow_paths:
            self._log("[FW] No privacy binary was found; kill switch not enabled.")
            return False
        data = self._snapshot()
        if data is None:
            self._log("[FW] Kill switch not enabled (could not save current rules).")
            return False
        self._remove_rules()
        self._transparent = bool(transparent)
        self._add_rules()
        if not self._transparent:
            if not self._block_defaults():
                self._remove_rules()
                self._restore_defaults()
                return False
        self._applied = True
        if self._transparent:
            # Windows Firewall evaluates outbound packets *before* WinDivert.
            # Blocking here would stop non-allowed applications from ever
            # reaching ProxyBridge, so the redirector itself enforces the
            # policy (TCP -> Tor, UDP blocked) while transparent mode is on.
            self._log("[FW] Transparent mode: Windows Firewall left in allow "
                      "mode; ProxyBridge enforces Tor routing and UDP blocking.")
        else:
            self._log("[FW] Kill switch enabled: outbound traffic blocked except "
                      "Tor / DNS / I2P.")
        return True

    def enable_block(self) -> bool:
        """Turn the default-Block kill switch on (transparent-mode fallback)."""
        if not is_admin():
            self._log("[FW] Not elevated — cannot enable the kill switch.")
            return False
        self._transparent = False
        ok = self._block_defaults()
        if ok:
            self._log("[FW] Kill switch enabled: outbound traffic blocked except "
                      "Tor / DNS / I2P.")
        return ok

    def remove(self) -> bool:
        if not self._applied and not _BACKUP.exists():
            return True
        if not is_admin():
            self._log("[FW] Not elevated — cannot restore the Windows Firewall "
                      "defaults. Run scripts\\restore-windows.ps1 as Administrator.")
            return False
        self._remove_rules()
        restored = self._restore_defaults()
        self._applied = False
        self._transparent = False
        if restored:
            try:
                _BACKUP.unlink()
            except OSError:
                pass
            self._log("[FW] Kill switch disabled and Windows Firewall defaults restored.")
        else:
            self._log("[FW] Firewall defaults were NOT restored; the snapshot was "
                      "kept. Run scripts\\restore-windows.ps1 as Administrator.")
        return restored

    def reapply_if_missing(self) -> bool:
        if not self._applied:
            return False
        script = (
            "$n = @(Get-NetFirewallRule -Group " + _q(_GROUP) +
            " -ErrorAction SilentlyContinue).Count; "
            "$bad = @(Get-NetFirewallProfile | Where-Object "
            "{ [string]$_.DefaultOutboundAction -ne 'Block' }).Count; "
            "Write-Output \"$n/$bad\""
        )
        rc, out = self._ps(script, timeout=20)
        if rc != 0:
            return False
        try:
            last = out.strip().splitlines()[-1]
            rules, bad = (int(x) for x in last.split("/", 1))
        except Exception:
            return False
        if rules == 0 or (bad > 0 and not self._transparent):
            self._log("[FW] Firewall rules changed — re-applying the kill switch.")
            self._remove_rules()
            self._add_rules()
            if not self._transparent:
                self._block_defaults()
        return True

    def heal(self) -> bool:
        """Remove rules and restore defaults after a crash.

        Returns True when there was nothing to repair or the repair succeeded.
        The snapshot is deliberately kept when the restore fails (for example
        because the process is not elevated) so a later run can retry instead
        of losing the only copy of the user's original firewall policy.
        """
        if not _BACKUP.exists():
            return True
        if not is_admin():
            self._log("[FW] Not elevated — the saved firewall policy was kept. "
                      "Run scripts\\restore-windows.ps1 as Administrator.")
            return False
        self._log("[FW] Repairing firewall state from a previous session…")
        self._remove_rules()
        restored = self._restore_defaults()
        self._applied = False
        self._transparent = False
        if restored:
            try:
                _BACKUP.unlink()
            except OSError:
                pass
        else:
            self._log("[FW] The firewall policy could not be restored; the "
                      "snapshot was kept for a later retry.")
        return restored
