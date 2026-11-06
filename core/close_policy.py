"""Window-close policy.

Kept free of Qt imports so the rule can be unit-tested without a GUI.

The X button has two jobs:

* while a connection is active (or a connect/disconnect is in flight) it must
  **hide** the window, otherwise closing it would silently tear down Tor and
  the kill switch;
* when nothing is protecting the system it should **quit**, which is what users
  expect from a close button.
"""
from __future__ import annotations


def quit_on_close(connected: bool, worker_running: bool) -> bool:
    """Return True when closing the window should exit the app."""
    return not connected and not worker_running
