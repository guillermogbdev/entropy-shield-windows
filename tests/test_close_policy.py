"""Tests for the window-close policy.

X must quit when the app is idle (what users expect) but hide to the tray while
protection is active, so closing the window cannot silently tear down the
tunnel or the kill switch.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.close_policy import quit_on_close  # noqa: E402


class ClosePolicyTest(unittest.TestCase):
    def test_idle_close_quits(self) -> None:
        self.assertTrue(quit_on_close(connected=False, worker_running=False))

    def test_connected_close_hides(self) -> None:
        self.assertFalse(quit_on_close(connected=True, worker_running=False))

    def test_close_during_connect_or_disconnect_hides(self) -> None:
        self.assertFalse(quit_on_close(connected=False, worker_running=True))
        self.assertFalse(quit_on_close(connected=True, worker_running=True))


if __name__ == "__main__":
    unittest.main()
