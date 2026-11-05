"""Connection orchestration for the Windows backend."""
from __future__ import annotations

import threading
from typing import Callable

from core.config import cfg, cfg_port

from . import netconfig
from .dns_forwarder import DnsForwarder
from .dnscrypt import WindowsDNSCryptManager
from .firewall import WindowsFirewallManager
from .i2p import WindowsI2PManager
from .mac import WindowsMacRandomizer
from .onion_server import WindowsOnionServerManager
from .tor import WindowsTorManager
from .transparent import WindowsTransparentManager


class WindowsConnectionManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._tor = WindowsTorManager(log)
        self._dns = WindowsDNSCryptManager(log)
        self._i2p = WindowsI2PManager(log)
        self._onion = WindowsOnionServerManager(log)
        self._fw = WindowsFirewallManager(log)
        self._forwarder = DnsForwarder(log)
        self._transparent = WindowsTransparentManager(log)
        self._transparent_active = False
        self._mac = WindowsMacRandomizer(log)
        self._layers: dict[str, bool] = {}
        self._configured = {"tor": False, "dnscrypt": False,
                            "i2p": False, "onion_server": False}
        self._watchdog_stop: threading.Event | None = None
        self._dns_changed = False
        self._proxy_changed = False

    # ── watchdog ────────────────────────────────────────────────────────────
    def _start_watchdog(self) -> None:
        stop = threading.Event()
        self._watchdog_stop = stop

        def _run() -> None:
            while not stop.wait(5):
                try:
                    self._fw.reapply_if_missing()
                except Exception as exc:
                    self._log(f"[FW] Watchdog could not re-apply rules: {exc}")
                if (self._transparent_active
                        and not self._transparent.is_running()):
                    self._log("[TRANSPARENT] ProxyBridge stopped unexpectedly — "
                              "enabling the firewall kill switch.")
                    self._transparent_active = False
                    try:
                        self._fw.enable_block()
                    except Exception as exc:
                        self._log(f"[FW] Watchdog could not block traffic: {exc}")

        threading.Thread(target=_run, name="fw-watchdog", daemon=True).start()

    def _stop_watchdog(self) -> None:
        if self._watchdog_stop is not None:
            self._watchdog_stop.set()
            self._watchdog_stop = None

    # ── public API ──────────────────────────────────────────────────────────
    def connect(self, use_tor: bool, use_dnscrypt: bool, use_i2p: bool,
                use_onion_server: bool = False) -> None:
        if use_onion_server:
            use_tor = True
        if not (use_tor or use_dnscrypt or use_i2p):
            raise ValueError("Select at least one privacy layer.")
        if use_tor and not self._tor.is_installed():
            raise RuntimeError(
                "tor.exe was not found. Run scripts/setup-windows.ps1, install "
                "Tor Browser, or put tor.exe in bin\\tor.")
        if use_dnscrypt and not self._dns.is_installed():
            raise RuntimeError(
                "dnscrypt-proxy.exe was not found. Run scripts/setup-windows.ps1 "
                "or put it in bin\\dnscrypt-proxy.")
        if use_i2p and not self._i2p.is_installed():
            raise RuntimeError(
                "i2pd.exe was not found. Run scripts/setup-windows.ps1 or put "
                "it in bin\\i2pd.")

        self._layers = {}
        self._configured = {"tor": False, "dnscrypt": False,
                            "i2p": False, "onion_server": False}
        try:
            self._do_connect(use_tor, use_dnscrypt, use_i2p, use_onion_server)
        except Exception:
            self._log("[!] Connect failed — rolling back all changes...")
            self._rollback(use_tor, use_dnscrypt, use_i2p, use_onion_server)
            raise

    def _do_connect(self, use_tor: bool, use_dnscrypt: bool, use_i2p: bool,
                    use_onion_server: bool) -> None:
        if cfg().get("mac_randomize"):
            self._mac.randomize()

        # ── configure everything first ──────────────────────────────────────
        if use_tor:
            self._tor.configure()
            self._configured["tor"] = True
        if use_onion_server:
            self._onion.configure(self._tor.torrc_path)
            self._configured["onion_server"] = True
        if use_dnscrypt:
            self._dns.configure(via_tor=use_tor,
                                tor_socks=cfg_port("tor", "socks_port"))
            self._configured["dnscrypt"] = True
        if use_i2p:
            self._i2p.configure(use_tor=use_tor)
            self._configured["i2p"] = True

        # The HTTP server must be listening before Tor publishes the service.
        if use_onion_server:
            self._onion.start()

        # ── kill switch before any service reaches the network ──────────────
        transparent_requested = bool(
            use_tor and cfg().get("windows", "transparent_tor")
            and self._transparent.installed())
        fw_ok = self._fw.apply(use_tor, use_dnscrypt, use_i2p,
                               transparent=transparent_requested)
        if not fw_ok and cfg().get("kill_switch"):
            raise RuntimeError(
                "The Windows Firewall kill switch could not be enabled. "
                "Check that the Windows Firewall service is running, or turn "
                "off Kill Switch in Settings if you accept the risk.")

        # ── start services ──────────────────────────────────────────────────
        # ProxyBridge goes first: its process tracker needs to be warm before
        # Tor starts opening circuits, otherwise Tor's own connections can be
        # caught by the wildcard rule and loop back into Tor.
        if use_tor:
            self._transparent_active = self._transparent.start()
            if transparent_requested and not self._transparent_active:
                # ProxyBridge could not start; fall back to the firewall kill
                # switch so applications cannot leave directly.
                self._fw.enable_block()

        if use_tor:
            self._tor.start()
            self._layers["tor"] = True

        if use_dnscrypt:
            self._dns.start()
            self._layers["dnscrypt"] = True

        if use_i2p:
            self._i2p.start(transparent=False)
            self._layers["i2p"] = True

        # ── DNS: system resolver → local relay → Tor DNSPort / DNSCrypt ─────
        upstream = cfg_port("dnscrypt", "port") if use_dnscrypt else cfg_port("tor", "dns_port")
        if use_tor or use_dnscrypt:
            if not self._forwarder.start(upstream):
                raise RuntimeError(
                    "Could not start the local DNS relay on 127.0.0.1:53. "
                    "Another DNS service may be using port 53; stop it and "
                    "try again, because DNS would otherwise leak.")
            # Mark this before the call: set_system_dns saves the snapshot
            # first, so even a partial failure must be reverted on disconnect.
            self._dns_changed = True
            if not netconfig.set_system_dns(self._log):
                raise RuntimeError(
                    "Could not point the system DNS at the local privacy "
                    "resolver. The connection was cancelled to avoid a DNS leak.")
            netconfig.flush_dns()

        # ── system proxy ───────────────────────────────────────────────────
        if use_tor:
            self._proxy_changed = True
            netconfig.set_system_proxy(
                f"socks=127.0.0.1:{cfg_port('tor', 'socks_port')}", self._log)
        elif use_i2p:
            port = cfg_port("i2p", "http_port")
            self._proxy_changed = True
            netconfig.set_system_proxy(
                f"http=127.0.0.1:{port};https=127.0.0.1:{port}", self._log)
        if not (use_tor or use_dnscrypt) and use_i2p:
            self._log("[INFO] I2P is running in proxy mode; configure apps to use "
                      f"HTTP 127.0.0.1:{cfg_port('i2p', 'http_port')} or SOCKS "
                      f"127.0.0.1:{cfg_port('i2p', 'socks_port')}.")

        if use_onion_server:
            self._layers["onion_server"] = True
            addr = self._onion.onion_address(wait=10)
            if addr:
                self._log(f"[ONION] Your .onion address: {addr}")
            else:
                self._log("[ONION] .onion address not ready yet. Check the "
                          "activity log after Tor finishes bootstrapping.")

        self._start_watchdog()
        self._log("[OK] All selected layers are active.")
        if use_tor and self._transparent_active:
            self._log("[INFO] Transparent Tor is active: applications that ignore "
                      "the Windows proxy are still routed through Tor. UDP is "
                      "blocked to prevent leaks.")
        elif use_tor:
            self._log("[INFO] Tor is running in SOCKS/system-proxy mode. Apps "
                      "that ignore the Windows proxy are kept in by the kill "
                      "switch, but do not route through Tor. Install ProxyBridge "
                      "and run as Administrator for transparent mode.")

    # ── teardown ────────────────────────────────────────────────────────────
    def _rollback(self, use_tor: bool, use_dnscrypt: bool,
                  use_i2p: bool, use_onion_server: bool) -> None:
        self._stop_watchdog()
        try:
            self._transparent.stop()
        except Exception:
            pass
        self._transparent_active = False
        try:
            if self._proxy_changed:
                netconfig.restore_system_proxy(self._log)
        except Exception:
            pass
        try:
            if self._dns_changed:
                netconfig.restore_system_dns(self._log)
            self._forwarder.stop()
        except Exception:
            pass
        try:
            self._fw.remove()
        except Exception:
            pass
        if use_onion_server:
            try:
                self._onion.stop()
            except Exception:
                pass
        if use_i2p and self._configured.get("i2p"):
            try:
                self._i2p.stop()
            except Exception:
                pass
        if use_dnscrypt and self._configured.get("dnscrypt"):
            try:
                self._dns.stop()
            except Exception:
                pass
        if use_tor and self._configured.get("tor"):
            try:
                self._tor.stop()
            except Exception:
                pass
        try:
            self._mac.restore()
        except Exception:
            pass

    def disconnect(self) -> None:
        self._stop_watchdog()
        try:
            self._transparent.stop()
        except Exception:
            pass
        self._transparent_active = False
        try:
            netconfig.restore_system_proxy(self._log)
        except Exception:
            pass
        try:
            netconfig.restore_system_dns(self._log)
        except Exception:
            pass
        try:
            self._fw.remove()
        except Exception:
            pass
        self._forwarder.stop()
        if self._layers.get("onion_server"):
            try:
                self._onion.stop()
            except Exception:
                pass
        if self._layers.get("i2p"):
            try:
                self._i2p.stop()
            except Exception:
                pass
        if self._layers.get("dnscrypt"):
            try:
                self._dns.stop()
            except Exception:
                pass
        if self._layers.get("tor"):
            try:
                self._tor.stop()
            except Exception:
                pass
        self._layers.clear()
        self._dns_changed = False
        self._proxy_changed = False
        try:
            self._mac.restore()
        except Exception:
            pass
        self._log("[OK] All layers disconnected.")
