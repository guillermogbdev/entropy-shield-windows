"""Run an application with its traffic sent through Tor (Windows).

Windows has no unprivileged network namespaces, so this backend combines two
mechanisms:

* a dedicated browser profile with explicit SOCKS flags (works without admin);
* a scoped ProxyBridge/WinDivert instance, started by the elevated helper,
  that redirects only that executable's TCP through Tor and blocks its public
  UDP.  Everything else stays DIRECT.

If the elevated helper is unavailable, it falls back to proxy environment
variables.  The caller watches ProxyBridge and terminates the app if it dies,
so the per-app mode is fail-closed.
"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

from core.config import cfg, cfg_port

from . import client, paths

_PRIVATE_SOCKS = 19050
_PRIVATE_CTRL = 19051
_PRIVATE_PROC: subprocess.Popen | None = None
_SESSIONS = paths.data_dir() / "torify-sessions.json"
_LOCK = threading.Lock()

_FIREFOX_PREFS = """\
user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", {socks});
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "127.0.0.1,localhost,::1");
user_pref("media.peerconnection.enabled", false);
user_pref("network.trr.mode", 5);
user_pref("network.dns.disablePrefetch", true);
user_pref("browser.startup.homepage", "about:blank");
"""


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.6):
            return True
    except OSError:
        return False


def _stop_private_at_exit() -> None:
    if _PRIVATE_PROC and _PRIVATE_PROC.poll() is None:
        try:
            _PRIVATE_PROC.terminate()
        except Exception:
            pass
    try:
        client.control_request("torify_stop", timeout=8, start=False)
    except Exception:
        pass


atexit.register(_stop_private_at_exit)


def _log(msg: str) -> None:
    """Best-effort log for the detached torify worker (no GUI callback here)."""
    try:
        paths.ensure_dirs()
        with open(paths.data_dir() / "torify.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _proxybridge_running() -> bool:
    """True when the system-wide transparent stack already owns WinDivert."""
    try:
        r = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq ProxyBridge_CLI.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=paths.no_window_flags())
        return "ProxyBridge_CLI.exe" in (r.stdout or "")
    except Exception:
        return False


def _torify_profile(exe: str, socks: int) -> Path:
    from .transparent import build_torify_profile
    paths.ensure_dirs()
    p = paths.data_dir() / f"torify-{uuid.uuid4().hex[:8]}.json"
    p.write_text(json.dumps(build_torify_profile(exe, socks), indent=2),
                 encoding="utf-8")
    return p


def _kill_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill.exe", "/T", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=15,
                       creationflags=paths.no_window_flags())
    except Exception:
        pass


def _watch(proc: subprocess.Popen, pb_pid: int, profile: Path) -> None:
    """Kill the app if ProxyBridge dies (fail-closed), then clean up."""
    try:
        while proc.poll() is None:
            if not _pid_alive(pb_pid):
                _log(f"ProxyBridge {pb_pid} died — terminating PID {proc.pid} "
                     "to avoid a direct leak.")
                _kill_tree(proc.pid)
                break
            time.sleep(1)
    finally:
        try:
            client.control_request("torify_stop", timeout=15, start=False)
        except Exception:
            pass
        try:
            profile.unlink()
        except OSError:
            pass


def _start_private_tor() -> int:
    global _PRIVATE_PROC
    if _port_open(_PRIVATE_SOCKS):
        return _PRIVATE_SOCKS
    tor = paths.find_binary("tor.exe", "tor")
    if not tor:
        raise RuntimeError("tor.exe was not found.")
    data = paths.data_dir() / "torify-private"
    data.mkdir(parents=True, exist_ok=True)
    torrc = data / "torrc"
    torrc.write_text(
        "\n".join([
            "# entropy-shield — private Tor for Run through Tor",
            f'DataDirectory "{str(data).replace(chr(92), "/")}"',
            # Tor's Log option does not accept quotes: with quotes it treats
            # them as part of the filename and aborts with "Invalid argument".
            "Log notice file "
            f"{str(data / 'tor.log').replace(chr(92), '/')}",
            f"SocksPort 127.0.0.1:{_PRIVATE_SOCKS} IsolateSOCKSAuth",
            f"ControlPort 127.0.0.1:{_PRIVATE_CTRL}",
            "CookieAuthentication 1",
            f'CookieAuthFile "{str(data / "control_auth_cookie").replace(chr(92), "/")}"',
            "VirtualAddrNetworkIPv4 10.192.0.0/10",
            "AutomapHostsOnResolve 1",
            "AutomapHostsSuffixes .onion,.exit",
            "",
        ]), encoding="utf-8")
    _PRIVATE_PROC = paths.popen(
        [tor, "-f", str(torrc)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 75
    while time.time() < deadline:
        if _PRIVATE_PROC.poll() is not None:
            tail = ""
            try:
                tail = (data / "tor.log").read_text(
                    encoding="utf-8", errors="replace")[-600:].strip()
            except OSError:
                pass
            raise RuntimeError("Private Tor exited during startup."
                               + (f" {tail}" if tail else ""))
        if _port_open(_PRIVATE_SOCKS):
            return _PRIVATE_SOCKS
        time.sleep(0.5)
    raise RuntimeError("Private Tor did not open its SocksPort.")


def _system_tor_socks() -> int | None:
    port = cfg_port("tor", "socks_port")
    return port if _port_open(port) else None


def ensure_tor() -> int:
    return _system_tor_socks() or _start_private_tor()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _read_sessions() -> list[dict]:
    try:
        data = json.loads(_SESSIONS.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


def _write_sessions(items: list[dict]) -> None:
    paths.ensure_dirs()
    tmp = _SESSIONS.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
    os.replace(tmp, _SESSIONS)


def _record(session: dict) -> None:
    with _LOCK:
        items = [s for s in _read_sessions() if _pid_alive(int(s.get("pid", 0)))]
        items.append(session)
        _write_sessions(items)


def _profile(name: str) -> Path:
    p = paths.data_dir() / "torify-profiles" / f"{name}-{uuid.uuid4().hex[:8]}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _browser_kind(exe: str) -> str:
    name = Path(exe).name.lower()
    if name in ("firefox.exe", "firefox-esr.exe", "librewolf.exe"):
        return "firefox"
    if name in ("msedge.exe", "chrome.exe", "brave.exe", "chromium.exe"):
        return "chromium"
    return ""


def _parse(args: list[str]) -> tuple[str, list[str]]:
    name = "Application"
    i = 0
    while i < len(args):
        if args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == "--desktop" and i + 1 < len(args):
            return name, [args[i + 1]]
        elif args[i] == "--":
            return name, args[i + 1:]
        elif args[i].startswith("--"):
            i += 1
        else:
            return name, args[i:]
    return name, []


def spawn(args: list[str], log=None) -> None:
    """Public entry point: never let a worker exception disappear silently."""
    try:
        _spawn_impl(args, log)
    except Exception as exc:
        _log(f"ERROR: {exc}")
        if log is not None:
            try:
                log(f"[BROWSER] Could not open the app through Tor: {exc}")
            except Exception:
                pass


def _spawn_impl(args: list[str], log=None) -> None:
    name, cmd = _parse(args)
    if not cmd:
        return
    socks = ensure_tor()
    exe = cmd[0]
    kind = _browser_kind(exe)
    env = dict(os.environ)

    # Prefer true per-app transparent routing through ProxyBridge.  When the
    # whole stack is already connected with transparent Tor, one instance is
    # enough; otherwise ask the elevated helper to start a scoped instance
    # that proxies only this executable.
    pb_pid: int | None = None
    profile: Path | None = None
    # Browsers already get an isolated profile with explicit SOCKS flags, and
    # a process-wide rule would also affect other running instances of the
    # same browser.  Use the scoped ProxyBridge only for non-browser apps.
    if not kind and not _proxybridge_running():
        try:
            profile = _torify_profile(exe, socks)
            label = f"{Path(exe).name}: TCP → Tor, UDP blocked"
            reply = client.control_request(
                "torify_start " + json.dumps(
                    {"profile": str(profile), "label": label}),
                timeout=20.0)
            if reply.get("ok"):
                pb_pid = int(reply.get("pid") or 0) or None
                _log(f"transparent per-app active for {exe} "
                     f"(ProxyBridge {pb_pid})")
            else:
                _log("per-app transparent unavailable: "
                     f"{reply.get('error')}; using proxy env/profile")
                profile.unlink(missing_ok=True)
                profile = None
        except Exception as exc:
            _log(f"per-app transparent error: {exc}")
            if profile is not None:
                try:
                    profile.unlink()
                except OSError:
                    pass
                profile = None

    if kind == "firefox":
        prof = _profile("firefox")
        (prof / "user.js").write_text(_FIREFOX_PREFS.format(socks=socks),
                                      encoding="utf-8")
        cmd = [exe, "--no-remote", "--profile", str(prof), *cmd[1:]]
    elif kind == "chromium":
        prof = _profile("chromium")
        cmd = [
            exe,
            f"--proxy-server=socks5://127.0.0.1:{socks}",
            "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE localhost",
            f"--user-data-dir={prof}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--incognito", *cmd[1:],
        ]
    else:
        proxy = f"socks5h://127.0.0.1:{socks}"
        for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                    "HTTPS_PROXY", "https_proxy"):
            env[key] = proxy
        env["NO_PROXY"] = "localhost,127.0.0.1,::1"
        env["no_proxy"] = env["NO_PROXY"]
    try:
        # Console apps (cmd/powershell) need their own console window: the GUI
        # has none, and without CREATE_NEW_CONSOLE they start and exit
        # immediately.  GUI browsers must keep the hidden/normal launch path.
        console = Path(exe).name.lower() in (
            "cmd.exe", "powershell.exe", "pwsh.exe")
        kwargs = {"cwd": str(Path.home()), "env": env}
        if console:
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            kwargs.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception:
        if profile is not None:
            try:
                profile.unlink()
            except OSError:
                pass
        if pb_pid:
            client.control_request("torify_stop", timeout=15, start=False)
        raise
    if pb_pid and profile is not None:
        threading.Thread(target=_watch, args=(proc, pb_pid, profile),
                         name="torify-watch", daemon=True).start()
    _record({
        "app": name or Path(exe).name,
        "pid": proc.pid,
        "started": time.time(),
        "socks": socks,
        "isolated": bool(kind),
        "transparent": bool(pb_pid),
        "via": "system" if _system_tor_socks() else "private",
    })


def _control_port() -> int | None:
    if _port_open(cfg_port("tor", "control_port")):
        return cfg_port("tor", "control_port")
    if _port_open(_PRIVATE_CTRL):
        return _PRIVATE_CTRL
    return None


def _newnym() -> bool:
    port = _control_port()
    if port is None:
        return False
    if port == _PRIVATE_CTRL:
        data = paths.data_dir() / "torify-private"
    else:
        data = paths.data_dir() / "tor-data"
    try:
        cookie = (data / "control_auth_cookie").read_bytes().hex()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(f"AUTHENTICATE {cookie}\r\n".encode())
            if not s.recv(1024).startswith(b"250"):
                return False
            s.sendall(b"SIGNAL NEWNYM\r\n")
            return s.recv(1024).startswith(b"250")
    except Exception:
        return False


def request(op: dict) -> dict:
    """Small compatibility layer for the existing TorifyPanel."""
    action = op.get("op")
    if action == "list":
        with _LOCK:
            items = [s for s in _read_sessions()
                     if _pid_alive(int(s.get("pid", 0)))]
            _write_sessions(items)
        return {"ok": True, "sessions": items}
    if action == "new_identity":
        return {"ok": _newnym()}
    if action == "end":
        return {"ok": True}
    return {"ok": True}
