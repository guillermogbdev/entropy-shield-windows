"""Isolated browser profiles for the Windows build."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import paths

_FIREFOX_TOR = """\
user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", {socks_port});
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "127.0.0.1,localhost,::1");
user_pref("network.dns.disablePrefetch", true);
user_pref("network.dns.disablePrefetchFromHTTPS", true);
user_pref("network.prefetch-next", false);
user_pref("network.predictor.enabled", false);
user_pref("network.http.speculative-parallel-limit", 0);
user_pref("network.proxy.failover_direct", false);
user_pref("network.proxy.allow_bypass", false);
user_pref("network.trr.mode", 5);
user_pref("network.http.http3.enable", false);
user_pref("media.peerconnection.enabled", false);
user_pref("geo.enabled", false);
user_pref("browser.send_pings", false);
user_pref("browser.startup.homepage", "about:blank");
"""

_FIREFOX_I2P = """\
user_pref("network.proxy.type", 1);
user_pref("network.proxy.http", "127.0.0.1");
user_pref("network.proxy.http_port", {http_port});
user_pref("network.proxy.ssl", "127.0.0.1");
user_pref("network.proxy.ssl_port", {http_port});
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", {socks_port});
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "127.0.0.1,localhost,::1");
user_pref("network.dns.disablePrefetch", true);
user_pref("network.dns.disablePrefetchFromHTTPS", true);
user_pref("network.prefetch-next", false);
user_pref("network.predictor.enabled", false);
user_pref("network.http.speculative-parallel-limit", 0);
user_pref("network.proxy.failover_direct", false);
user_pref("network.proxy.allow_bypass", false);
user_pref("network.trr.mode", 5);
user_pref("network.http.http3.enable", false);
user_pref("media.peerconnection.enabled", false);
user_pref("geo.enabled", false);
user_pref("browser.send_pings", false);
user_pref("browser.startup.homepage", "http://127.0.0.1:{http_port}");
"""


def _profile(name: str) -> Path:
    p = paths.data_dir() / "profiles" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _spawn(cmd: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.Popen(
        cmd,
        cwd=str(Path.home()),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_tor(socks_port: int, log: Callable[[str], None]) -> None:
    found = paths.find_any_browser()
    if not found:
        raise RuntimeError(
            "No supported browser found. Install Firefox, Chrome, Edge or Brave.")
    exe, kind = found
    if kind == "firefox":
        prof = _profile("firefox-tor")
        (prof / "user.js").write_text(
            _FIREFOX_TOR.format(socks_port=socks_port), encoding="utf-8")
        _spawn([exe, "--no-remote", "--profile", str(prof)])
        log(f"[BROWSER] Firefox launched via Tor (profile: {prof}).")
        return
    prof = _profile(f"{kind}-tor")
    _spawn([
        exe,
        f"--proxy-server=socks5://127.0.0.1:{socks_port}",
        "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE localhost",
        f"--user-data-dir={prof}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-sync", "--incognito",
    ])
    log(f"[BROWSER] {Path(exe).name} launched via Tor.")


def launch_i2p(http_port: int, socks_port: int,
               log: Callable[[str], None]) -> None:
    found = paths.find_any_browser()
    if not found:
        raise RuntimeError(
            "No supported browser found. Install Firefox, Chrome, Edge or Brave.")
    exe, kind = found
    if kind == "firefox":
        prof = _profile("firefox-i2p")
        (prof / "user.js").write_text(
            _FIREFOX_I2P.format(http_port=http_port, socks_port=socks_port),
            encoding="utf-8")
        _spawn([exe, "--no-remote", "--profile", str(prof)])
        log(f"[BROWSER] Firefox launched via I2P (profile: {prof}).")
        return
    prof = _profile(f"{kind}-i2p")
    _spawn([
        exe,
        f"--proxy-server=http://127.0.0.1:{http_port}",
        f"--user-data-dir={prof}",
        "--no-first-run", "--no-default-browser-check", "--disable-sync",
    ])
    log(f"[BROWSER] {Path(exe).name} launched via I2P.")


def launch_proxy_terminal(socks_port: int, log: Callable[[str], None]) -> None:
    env = dict(os.environ)
    url = f"socks5h://127.0.0.1:{socks_port}"
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                "HTTPS_PROXY", "https_proxy"):
        env[key] = url
    env["NO_PROXY"] = "localhost,127.0.0.1,::1"
    env["no_proxy"] = env["NO_PROXY"]
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    _spawn([comspec], env=env)
    log("[TERMINAL] Command Prompt launched with Tor proxy environment.")
    log("[TERMINAL] Note: only programs that honour proxy environment variables "
        "use Tor; this is not a network namespace.")
