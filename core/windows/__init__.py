"""Windows backend for Entropy Shield.

The Linux application controls nftables, systemd and a root daemon.  None of
those exist on Windows, so this package provides equivalents that keep the GUI
and the line protocol unchanged:

* a small elevated helper process (started with UAC on demand) performs the
  operations that need Administrator rights;
* Tor and DNSCrypt/i2pd run as ordinary child processes;
* system DNS is pointed at a local DNS forwarder that relays to Tor's DNSPort
  or to dnscrypt-proxy, and restored on disconnect;
* the Windows Firewall implements the kill switch by switching the default
  outbound action to Block and allowing only the privacy binaries.
"""
from __future__ import annotations

import os

IS_WINDOWS = os.name == "nt"
