"""Tests for keeping a persistent helper alive across GUI exits.

A helper started by the logon task must survive the GUI quitting, otherwise the
next Connect would ask for UAC again.  A helper started on demand with UAC keeps
the old behaviour and is shut down.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    from core.windows import client, daemon_win


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class HelperPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "daemon.json"
        self._old_client = client._CONTROL
        self._old_daemon = daemon_win._CONTROL
        self._old_persist = daemon_win._PERSIST
        client._CONTROL = self.path
        daemon_win._CONTROL = self.path

    def tearDown(self) -> None:
        client._CONTROL = self._old_client
        daemon_win._CONTROL = self._old_daemon
        daemon_win._PERSIST = self._old_persist
        self._tmp.cleanup()

    def test_logon_task_helper_is_persistent(self) -> None:
        daemon_win._PERSIST = True
        daemon_win._write_control(41234, "token123")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(raw["persist"])
        self.assertTrue(client.helper_persistent())

    def test_on_demand_helper_is_not_persistent(self) -> None:
        daemon_win._PERSIST = False
        daemon_win._write_control(41234, "token123")
        self.assertFalse(client.helper_persistent())

    def test_missing_control_file_is_not_persistent(self) -> None:
        self.assertFalse(client.helper_persistent())


if __name__ == "__main__":
    unittest.main()
