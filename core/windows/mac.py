"""MAC address randomization for Windows Wi-Fi profiles.

Windows has a native, driver-independent implementation: the per-profile
``MAC Randomization`` setting managed by the WLAN service.  Enabling it makes
Windows re-associate with a locally administered random MAC, and it survives
reboots without touching driver registry keys (which are per-vendor and often
require an adapter restart).

Only Wi-Fi is covered: Windows exposes no safe equivalent for Ethernet, so a
wired connection logs a clear message and stays unchanged.  Everything is
best-effort and opt-in (``mac_randomize`` defaults to false).
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Callable

from . import paths

_STATE = re.compile(
    r"(?:MAC Randomization|Aleatorizaci[oó]n de MAC)\s*:\s*(\w+)", re.I)
_SAFE = re.compile(r"^[A-Za-z0-9_. ()-]{1,64}$")


def _run(args: list[str], timeout: float = 20) -> str:
    try:
        r = subprocess.run(
            ["netsh", "wlan", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=paths.no_window_flags(),
        )
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


class WindowsMacRandomizer:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._saved: dict[tuple[str, str], str] = {}

    # ── discovery ─────────────────────────────────────────────────────────
    @staticmethod
    def _connected() -> list[tuple[str, str]]:
        """Return (interface, SSID) for every connected Wi-Fi adapter."""
        text = _run(["show", "interfaces"])
        out: list[tuple[str, str]] = []
        iface = ssid = None
        state = None
        for line in text.splitlines() + [""]:
            s = line.strip()
            if not s:
                if iface and ssid and (state or "").lower() == "connected":
                    out.append((iface, ssid))
                iface = ssid = state = None
                continue
            if ":" not in s:
                continue
            key, value = s.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "name":
                iface = value
            elif key == "ssid":
                ssid = value
            elif key == "state":
                state = value
        return out

    @staticmethod
    def _state(iface: str, ssid: str) -> str | None:
        if not (_SAFE.match(iface) and _SAFE.match(ssid)):
            return None
        text = _run(["show", "profile", f"name={ssid}", f"interface={iface}"])
        m = _STATE.search(text)
        return m.group(1) if m else None

    @staticmethod
    def _set(iface: str, ssid: str, value: str) -> bool:
        if not (_SAFE.match(iface) and _SAFE.match(ssid)):
            return False
        if value not in ("yes", "no", "daily"):
            return False
        text = _run([
            "set", "profileparameter", f"name={ssid}",
            f"interface={iface}", f"randomization={value}",
        ])
        # netsh prints a localised confirmation; absence of "failed"/"error"
        # plus a readable state afterwards is the reliable check.
        if re.search(r"\b(failed|error|no se pudo)\b", text, re.I):
            return False
        return True

    # ── public API ────────────────────────────────────────────────────────
    def randomize(self) -> None:
        """Enable per-profile MAC randomization.  Never raises."""
        if os.name != "nt":
            return
        profiles = self._connected()
        if not profiles:
            self._log("[MAC] No connected Wi-Fi profile; MAC randomization skipped.")
            return
        for iface, ssid in profiles:
            state = self._state(iface, ssid)
            if state is None:
                self._log(f"[MAC] {iface} ({ssid}): profile does not expose MAC "
                          "randomization.")
                continue
            if state.lower().startswith("enabled") or state.lower() == "daily":
                self._log(f"[MAC] {iface} ({ssid}): already {state}.")
                continue
            self._saved[(iface, ssid)] = state
            if not self._set(iface, ssid, "yes"):
                self._saved.pop((iface, ssid), None)
                self._log(f"[MAC] {iface} ({ssid}): could not enable randomization.")
                continue
            actual = self._state(iface, ssid)
            if actual and actual.lower().startswith("enabled"):
                self._log(f"[MAC] {iface} ({ssid}): randomization enabled; "
                          "Windows will reconnect with a random MAC.")
            else:
                self._log(f"[MAC] {iface} ({ssid}): requested, current state is "
                          f"{actual or 'unknown'}.")

    def restore(self) -> None:
        """Restore the original per-profile setting.  Never raises."""
        if os.name != "nt":
            return
        for (iface, ssid), state in list(self._saved.items()):
            value = ("daily" if state.lower() == "daily"
                     else "yes" if state.lower().startswith("enabled") else "no")
            if self._set(iface, ssid, value):
                self._log(f"[MAC] {iface} ({ssid}): restored to {state}.")
            else:
                self._log(f"[MAC] {iface} ({ssid}): could not restore {state}; "
                          "set it manually in Wi-Fi settings if needed.")
        self._saved.clear()
