"""Tests for the Windows single-instance guard.

The important behaviour is cross-process: a second launch must be able to tell
the running instance to restore its window instead of exiting silently.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    from core.windows import singleton


def _fresh_name() -> str:
    return f"test-{os.getpid()}-{time.time_ns()}"


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class SingletonTest(unittest.TestCase):
    def _child(self, body: str) -> int:
        code = (f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
                f"from core.windows import singleton; {body}")
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True).returncode

    def test_names_are_per_user_and_session(self) -> None:
        mutex, event = singleton._names("gui")
        self.assertTrue(mutex.startswith("Local\\EntropyShield-gui-"))
        self.assertEqual(event, mutex + "-activate")

    def test_second_process_cannot_acquire(self) -> None:
        name = _fresh_name()
        self.assertTrue(singleton.acquire(name))
        try:
            rc = self._child(
                f"raise SystemExit(3 if not singleton.acquire({name!r}) else 0)")
            self.assertEqual(rc, 3)
        finally:
            singleton.release(name)
        # Once released, a new process can take over.
        rc = self._child(
            f"raise SystemExit(0 if singleton.acquire({name!r}) else 3)")
        self.assertEqual(rc, 0)

    def test_second_process_signals_activation(self) -> None:
        name = _fresh_name()
        self.assertTrue(singleton.acquire(name))
        try:
            self.assertFalse(singleton.consume_activation(name))
            rc = self._child(
                "raise SystemExit("
                f"0 if singleton.request_activation({name!r}) else 1)")
            self.assertEqual(rc, 0)
            # Auto-reset event: exactly one request per launch.
            self.assertTrue(singleton.consume_activation(name))
            self.assertFalse(singleton.consume_activation(name))
        finally:
            singleton.release(name)

    def test_activation_without_running_instance_fails(self) -> None:
        name = _fresh_name()
        self.assertFalse(singleton.request_activation(name))


if __name__ == "__main__":
    unittest.main()
