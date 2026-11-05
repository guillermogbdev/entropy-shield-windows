"""System DNS and WinINET proxy configuration (restored on disconnect).

The helper runs elevated.  DNS is changed with ``netsh`` because the
``Set-DnsClientServerAddress`` cmdlet has no ``-AddressFamily`` parameter and
its CIM calls fail in ways that are hard to distinguish from a permissions
problem.  A snapshot is written to disk *before* a change, which lets the next
helper startup repair state left behind by a crash or a forced reboot.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import tempfile
import winreg
from pathlib import Path
from typing import Callable

from .admin import is_admin
from .paths import data_dir, no_window_flags

_PS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]
_DNS_BACKUP = data_dir() / "dns-backup.json"
_PROXY_BACKUP = data_dir() / "proxy-backup.json"
_INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_PROXY_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


def _ps(script: str, timeout: float = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            [*_PS, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=no_window_flags(),
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as exc:
        return 1, "", str(exc)


def _ps_json(script: str, timeout: float = 30) -> object | None:
    """Run PowerShell and parse a JSON document written to a temp file.

    Writing to a file avoids the console code-page ambiguity that affects
    redirected PowerShell output on some Windows installations.
    """
    data_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="entropy-shield-ps-", suffix=".json",
                               dir=str(data_dir()))
    os.close(fd)
    try:
        escaped = tmp.replace("'", "''")
        full = (
            "$ErrorActionPreference='Stop'; & { "
            + script
            + f" }} | ConvertTo-Json -Depth 6 -Compress | Set-Content -LiteralPath '{escaped}' -Encoding UTF8"
        )
        rc, _out, err = _ps(full, timeout=timeout)
        if rc != 0:
            return None
        raw = Path(tmp).read_text(encoding="utf-8-sig").strip()
        if not raw or raw.lower() == "null":
            return None
        return json.loads(raw)
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _q(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _netsh(args: list[str], timeout: float = 20) -> tuple[int, str]:
    """Run netsh with a hidden window and return (returncode, output)."""
    try:
        r = subprocess.run(
            ["netsh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=no_window_flags(),
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, out
    except Exception as exc:
        return 1, str(exc)


def _netsh_set_dns(alias: str, family: str, address: str) -> tuple[int, str]:
    return _netsh([
        "interface", family, "set", "dnsservers",
        f"name={alias}", "static", address, "primary",
    ])


def _netsh_reset_dns(alias: str, family: str) -> tuple[int, str]:
    return _netsh([
        "interface", family, "set", "dnsservers",
        f"name={alias}", "source=dhcp",
    ])


def _netsh_add_dns(alias: str, family: str, address: str, index: int) -> tuple[int, str]:
    return _netsh([
        "interface", family, "add", "dnsservers",
        f"name={alias}", f"address={address}", f"index={index}",
    ])


def _verify_dns() -> bool:
    """Read back the adapters and check that at least one uses 127.0.0.1."""
    after = get_dns_snapshot()
    if not after:
        return False
    return any("127.0.0.1" in (item.get("v4") or []) for item in after)


# ── DNS ──────────────────────────────────────────────────────────────────────

def get_dns_snapshot() -> list[dict] | None:
    script = r"""
$def4 = @((Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue).ifIndex)
$def6 = @((Get-NetRoute -DestinationPrefix '::/0' -ErrorAction SilentlyContinue).ifIndex)
$out = @()
foreach ($a in @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceAlias -ne 'Loopback Pseudo-Interface 1' })) {
    $v4 = @((Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses)
    $v6 = @((Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv6 -ErrorAction SilentlyContinue).ServerAddresses)
    $out += [pscustomobject]@{
        alias = [string]$a.InterfaceAlias
        if_index = [uint32]$a.ifIndex
        v4 = $v4
        v6 = $v6
        default = [bool]($def4 -contains $a.ifIndex -or $def6 -contains $a.ifIndex)
    }
}
$out
"""
    parsed = _ps_json(script)
    if parsed is None:
        return None
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return None
    out: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        alias = item.get("alias")
        if not isinstance(alias, str) or not alias:
            continue
        try:
            if_index = int(item.get("if_index") or 0)
        except (TypeError, ValueError):
            if_index = 0
        out.append({
            "alias": alias,
            "if_index": if_index,
            "default": bool(item.get("default")),
            "v4": [str(x) for x in (item.get("v4") or []) if str(x).strip()],
            "v6": [str(x) for x in (item.get("v6") or []) if str(x).strip()],
            "v4_source": _dns_source(alias, "ipv4"),
            "v6_source": _dns_source(alias, "ipv6"),
        })
    return out


def _dns_source(alias: str, family: str) -> str:
    """Return 'dhcp' or 'static' for an adapter's current DNS configuration."""
    rc, out = _netsh([
        "interface", family, "show", "dnsservers", f"name={alias}",
    ])
    if rc == 0 and "dhcp" in out.lower():
        return "dhcp"
    return "static"


def save_dns_snapshot(snapshot: list[dict]) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    tmp = _DNS_BACKUP.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    os.replace(tmp, _DNS_BACKUP)


def load_dns_snapshot() -> list[dict] | None:
    try:
        data = json.loads(_DNS_BACKUP.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except Exception:
        return None


def set_system_dns(log: Callable[[str], None] | None = None) -> bool:
    """Point every active adapter at the local forwarder (IPv4 and IPv6).

    ``netsh`` is used instead of ``Set-DnsClientServerAddress`` because the
    cmdlet throws a *terminating* error on an adapter that has no address of
    the requested family, which used to abort the whole loop before the Wi-Fi
    adapter was configured.  Each adapter is independent now, and the result is
    read back before the connection is allowed to continue.
    """
    snapshot = get_dns_snapshot()
    if snapshot is None:
        if log:
            log("[DNS] Could not read the current DNS settings — leaving them unchanged.")
        return False
    if not _DNS_BACKUP.exists():
        save_dns_snapshot(snapshot)

    aliases = [item["alias"] for item in snapshot if item.get("alias")]
    if not aliases:
        if log:
            log("[DNS] No active network adapter found.")
        return False

    errors: list[str] = []
    ok_v4 = 0
    for alias in aliases:
        rc, out = _netsh_set_dns(alias, "ipv4", "127.0.0.1")
        if rc == 0:
            ok_v4 += 1
        else:
            errors.append(f"{alias} IPv4: {out or f'rc {rc}'}")
        # IPv6 is best effort: some adapters have IPv6 disabled, and that is
        # not a reason to fail the whole connection.
        rc6, out6 = _netsh_set_dns(alias, "ipv6", "::1")
        if rc6 != 0:
            errors.append(f"{alias} IPv6: {out6 or f'rc {rc6}'}")

    if ok_v4 == 0 or not _verify_dns():
        if log:
            detail = "; ".join(errors[-4:]) if errors else "netsh did not apply the setting"
            log(f"[DNS] Could not set system DNS: {detail}")
        return False
    if log:
        log(f"[DNS] System DNS → 127.0.0.1 on {ok_v4} adapter(s).")
    return True


def restore_system_dns(log: Callable[[str], None] | None = None) -> bool:
    if not _DNS_BACKUP.exists():
        return True
    if not is_admin():
        if log:
            log("[DNS] Not elevated — the saved DNS settings were kept. "
                "Run scripts\\restore-windows.ps1 as Administrator.")
        return False
    snapshot = load_dns_snapshot()
    if snapshot is None:
        if log:
            log("[DNS] The saved DNS snapshot is unreadable; it was kept for a "
                "manual repair.")
        return False
    if not snapshot:
        try:
            _DNS_BACKUP.unlink()
        except OSError:
            pass
        return True
    errors: list[str] = []
    for item in snapshot:
        alias = item.get("alias")
        if not alias:
            continue
        for family, key in (("ipv4", "v4"), ("ipv6", "v6")):
            addresses = [x for x in (item.get(key) or []) if x]
            source = item.get(key + "_source", "static")
            if source == "dhcp" or not addresses:
                rc, out = _netsh_reset_dns(alias, family)
                if rc != 0:
                    errors.append(f"{alias} {family}: {out or f'rc {rc}'}")
                continue
            rc, out = _netsh_set_dns(alias, family, addresses[0])
            if rc != 0:
                errors.append(f"{alias} {family}: {out or f'rc {rc}'}")
                continue
            for idx, address in enumerate(addresses[1:], start=2):
                rc, out = _netsh_add_dns(alias, family, address, idx)
                if rc != 0:
                    errors.append(f"{alias} {family} #{idx}: {out or f'rc {rc}'}")
    if errors:
        # Keep the backup: the next helper start or the restore script can
        # retry instead of silently leaving the privacy DNS in place.
        if log:
            log("[DNS] Some DNS settings could not be restored: "
                + "; ".join(errors[-4:]))
        return False
    try:
        _DNS_BACKUP.unlink()
    except OSError:
        pass
    if log:
        log("[DNS] Original DNS settings restored.")
    return True


def flush_dns() -> None:
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True,
                       creationflags=no_window_flags(), timeout=10)
    except Exception:
        pass


# ── WinINET proxy (HKCU) ────────────────────────────────────────────────────

def _read_proxy_values() -> dict:
    out: dict[str, dict] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS) as key:
            for name in _PROXY_VALUES:
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                    out[name] = {"value": value, "kind": kind}
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    return out


def _notify_proxy_change() -> None:
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:
        pass


def set_system_proxy(proxy_server: str, log: Callable[[str], None] | None = None) -> bool:
    """Enable the per-user WinINET proxy and remember the previous values."""
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        if not _PROXY_BACKUP.exists():
            _PROXY_BACKUP.write_text(json.dumps(_read_proxy_values(), indent=2),
                                     encoding="utf-8")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS,
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ,
                              "<local>;127.*;localhost;::1")
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
        _notify_proxy_change()
        if log:
            log(f"[PROXY] Windows proxy → {proxy_server}")
        return True
    except Exception as exc:
        if log:
            log(f"[PROXY] Could not set the system proxy: {exc}")
        return False


def restore_system_proxy(log: Callable[[str], None] | None = None) -> bool:
    if not _PROXY_BACKUP.exists():
        return True
    try:
        raw = _PROXY_BACKUP.read_text(encoding="utf-8")
        saved = json.loads(raw)
    except Exception as exc:
        if log:
            log(f"[PROXY] The saved proxy snapshot is unreadable ({exc}); it was "
                "kept for a manual repair.")
        return False
    if not isinstance(saved, dict):
        saved = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS,
                            0, winreg.KEY_SET_VALUE) as key:
            for name in _PROXY_VALUES:
                item = saved.get(name)
                if isinstance(item, dict) and "value" in item:
                    winreg.SetValueEx(key, name, 0, int(item.get("kind", winreg.REG_SZ)),
                                      item["value"])
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        _notify_proxy_change()
    except Exception as exc:
        if log:
            log(f"[PROXY] Could not restore the Windows proxy settings: {exc}")
        return False
    try:
        _PROXY_BACKUP.unlink()
    except OSError:
        pass
    if log:
        log("[PROXY] Windows proxy settings restored.")
    return True


def heal(log: Callable[[str], None] | None = None) -> bool:
    """Undo DNS/proxy changes left by a previous crashed session.

    Returns True only when every existing snapshot was restored.  Failed
    snapshots are kept so the next elevated run can retry.
    """
    dns_ok = restore_system_dns(log)
    proxy_ok = restore_system_proxy(log)
    return dns_ok and proxy_ok
