"""Tests for the Windows transparent-Tor profile generation.

These are pure logic tests: no WinDivert, no Administrator rights, no network.
They pin the fail-closed shape of the profile that ProxyBridge loads.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import cfg  # noqa: E402
from core.windows.transparent import (  # noqa: E402
    WindowsTransparentManager, _LOCAL_HOSTS, _REFUSED_RE,
    build_torify_profile,
)


def _rules(profile: dict) -> list[tuple[str, str, str, str]]:
    return [(r["ProcessName"], r["Protocol"], r["Action"],
             r["TargetHosts"]) for r in profile["ProxyRules"]]


class TransparentProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._routing = dict(cfg().get("per_app_routing"))
        self._vpn = list(cfg().get("vpn", "allow"))
        cfg().set("per_app_routing", "enabled", False)
        cfg().set("per_app_routing", "rules", [])
        cfg().set("vpn", "allow", [])
        self.manager = WindowsTransparentManager(lambda _m: None)

    def tearDown(self) -> None:
        cfg().set("per_app_routing", "enabled", self._routing["enabled"])
        cfg().set("per_app_routing", "rules", self._routing["rules"])
        cfg().set("vpn", "allow", self._vpn)

    def test_fail_closed_defaults(self) -> None:
        rules = _rules(self.manager.build_profile())
        # Loopback UDP first so the local DNS relay keeps working.
        self.assertEqual(rules[0], ("*", "UDP", "DIRECT",
                                    "127.0.0.1;::1;localhost"))
        # WinDivert re-injects DIRECT packets as System; TCP must stay direct.
        self.assertIn(("System", "TCP", "DIRECT", "*"), rules)
        # Tor itself must never loop through Tor.
        self.assertIn(("tor.exe", "TCP", "DIRECT", "*"), rules)
        # Everything else: TCP through Tor, UDP blocked.
        self.assertIn(("*", "TCP", "PROXY", "*"), rules)
        self.assertIn(("*", "UDP", "BLOCK", "*"), rules)
        # Real LAN traffic stays direct, like the Linux ruleset.
        self.assertIn(("*", "TCP", "DIRECT", _LOCAL_HOSTS), rules)
        self.assertIn(("*", "UDP", "DIRECT", _LOCAL_HOSTS), rules)

    def test_vpn_endpoints_are_exempt(self) -> None:
        cfg().set("vpn", "allow", ["203.0.113.0/24"])
        rules = _rules(self.manager.build_profile())
        self.assertIn(("*", "TCP", "DIRECT", "203.0.113.0/24"), rules)
        self.assertIn(("*", "UDP", "DIRECT", "203.0.113.0/24"), rules)

    def test_torify_profile_only_targets_one_process(self) -> None:
        rules = _rules(build_torify_profile(
            r"C:\Program Files\Example\example.exe", 9050))
        self.assertIn(("example.exe", "TCP", "PROXY", "*"), rules)
        self.assertIn(("example.exe", "UDP", "BLOCK", "*"), rules)
        # Everything else stays direct: torify must not protect the whole PC.
        self.assertIn(("*", "TCP", "DIRECT", "*"), rules)
        self.assertIn(("*", "UDP", "DIRECT", "*"), rules)
        self.assertIn(("*", "TCP", "DIRECT", _LOCAL_HOSTS), rules)

    def test_per_app_actions_are_translated(self) -> None:
        cfg().set("per_app_routing", "enabled", True)
        cfg().set("per_app_routing", "rules", [
            {"name": "A", "uid_or_user": "firefox.exe", "action": "tor"},
            {"name": "B", "uid_or_user": "game.exe", "action": "direct"},
            {"name": "C", "uid_or_user": "tracker.exe", "action": "block"},
        ])
        rules = _rules(self.manager.build_profile())
        self.assertIn(("firefox.exe", "TCP", "PROXY", "*"), rules)
        self.assertIn(("firefox.exe", "UDP", "BLOCK", "*"), rules)
        self.assertIn(("game.exe", "TCP", "DIRECT", "*"), rules)
        self.assertIn(("game.exe", "UDP", "DIRECT", "*"), rules)
        self.assertIn(("tracker.exe", "TCP", "BLOCK", "*"), rules)
        self.assertIn(("tracker.exe", "UDP", "BLOCK", "*"), rules)

    def test_refused_endpoint_warning_regex(self) -> None:
        line = ("[LOG]  SOCKS5 IPv4: CONNECT to 129.241.121.18:443 failed - "
                "proxy replied 0x05 (connection refused)")
        self.assertEqual(_REFUSED_RE.findall(line), ["129.241.121.18:443"])

    def test_linux_uids_are_ignored(self) -> None:
        cfg().set("per_app_routing", "enabled", True)
        cfg().set("per_app_routing", "rules", [
            {"name": "uid", "uid_or_user": "1000", "action": "direct"},
        ])
        names = {r[0] for r in _rules(self.manager.build_profile())}
        self.assertNotIn("1000", names)


if __name__ == "__main__":
    unittest.main()
