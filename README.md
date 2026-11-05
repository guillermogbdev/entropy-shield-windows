<div align="center">

<img src="logos/oled.png" alt="Entropy Shield" width="110" />

# Entropy Shield — Windows

### Native Windows 10/11 port of the Entropy Shield privacy stack

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?style=flat-square&logo=windows&logoColor=white)](#requirements)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-41CD52?style=flat-square&logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Build](https://img.shields.io/badge/Build-portable%20EXE-0f172a?style=flat-square)](#build-a-portable-executable)
[![Windows build](https://github.com/guillermogbdev/entropy-shield-windows/actions/workflows/windows.yml/badge.svg?branch=main)](https://github.com/guillermogbdev/entropy-shield-windows/actions/workflows/windows.yml)

**One GUI to control Tor, DNSCrypt, I2P and onion services — with transparent, system-wide Tor routing on Windows.**

</div>

---

> ## Attribution
>
> This repository is a **native Windows adaptation** of
> **[Entropy Shield](https://github.com/berk-kucuk/entropy-shield)** by
> **[Berk Küçük](https://berkkucukk.com)**, used and redistributed under the
> MIT License.
>
> The upstream project is written for Linux. This port keeps the same PyQt6
> interface and rewrites the privileged backend for Windows (no systemd,
> `nftables`, `iptables` or Linux *network namespaces*). Linux support is not
> removed: the original modules remain in the tree.
>
> Original work: <https://github.com/berk-kucuk/entropy-shield>  
> Upstream author: <https://berkkucukk.com>  
> Upstream documentation retained in [`docs/README-LINUX.md`](docs/README-LINUX.md).

---

## What is this?

Entropy Shield bundles several anonymity and privacy layers behind a single
desktop application:

- **Tor** — SOCKS proxy, ControlPort and DNSPort, with circuit renewal.
- **Transparent Tor** — every TCP connection on the machine is redirected
  through Tor with **ProxyBridge / WinDivert**; UDP and QUIC/WebRTC are blocked.
- **DNSCrypt-proxy** — encrypted DNS, with the Windows resolver pointed at a
  local relay so queries cannot leak to the ISP.
- **I2P (i2pd)** — HTTP and SOCKS proxies, plus an optional transport routed
  through Tor.
- **Onion Server** — publish a local directory as a `.onion` service using the
  built-in HTTP server.
- **Kill switch** — Windows Firewall rules that block direct egress when the
  stack is connected.
- **Per-app routing** — send a given executable through Tor or keep it direct.
- **“Run any app through Tor”** — scoped ProxyBridge instance for a single
  process, without redirecting the rest of the system.
- **Isolated browser profiles** — dedicated Tor/I2P profiles for Firefox, Edge,
  Chrome and Brave.
- **Leak tests, circuit renewal, auto-connect, tray icon and themes.**

See the full feature matrix in [`README-WINDOWS.md`](README-WINDOWS.md).

---

## Requirements

| Component | Requirement |
|---|---|
| OS | Windows 10 or 11, 64-bit |
| Python | 3.10 or newer (tested with 3.14) |
| GUI | PyQt6 6.4+ (installed by the setup script) |
| Privacy binaries | Tor Expert Bundle, dnscrypt-proxy and i2pd (downloaded by the setup script) |
| Privileges | Administrator **only** for the elevated helper; the GUI runs as a normal user |

The app is **portable**: it does not need an installer, but installing it under
`Program Files` is recommended for daily use (see below).

---

## Quick start

Open PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

The script checks Python, installs PyQt6, downloads the official Tor Expert
Bundle, dnscrypt-proxy and i2pd into `bin\`, and installs ProxyBridge in
`%LOCALAPPDATA%\entropy-shield\proxybridge` for transparent mode. Some of these
steps may ask for UAC (ProxyBridge service registration).

Run the app:

```bat
run-windows.bat
```

To start directly in the system tray without a console window:

```bat
wscript run-windows-tray.vbs
```

### Build a portable executable

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

Output: `dist\Entropy Shield\Entropy Shield.exe`, with `bin\` copied next to it
so the frozen build can find Tor, DNSCrypt and i2pd.

### Install for daily use (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

This copies the app to `%ProgramFiles%\Entropy Shield`, creates a Start Menu
shortcut and registers the **Entropy Shield Helper** scheduled task. The helper
starts elevated at logon, so pressing **Connect** does not prompt for UAC.
Without that task (for example when running from `dist\`), the first Connect
prompts for UAC.

```powershell
# Register the helper task manually (optional)
powershell -ExecutionPolicy Bypass -File .\scripts\install-helper-task.ps1

# Uninstall (add -RemoveData to delete configuration, Tor cache and onion keys)
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ps1
```

> **Security note:** install under `Program Files`. If you run the EXE from a
> user-writable folder (Desktop, Downloads), a local process could modify the
> binary before you approve the helper's UAC prompt.

---

## How it works

```text
┌──────────────────────────────┐
│ GUI (normal user)            │
│  PyQt6, tray, themes         │
└──────────────┬───────────────┘
               │ line protocol on 127.0.0.1
               │ + random per-user token
┌──────────────▼───────────────┐
│ elevated helper (UAC)        │
│  · Windows Firewall          │
│  · system DNS                │
│  · WinINET proxy (HKCU)      │
│  · launches tor/dnscrypt/i2pd│
└──────────────┬───────────────┘
               │
      ┌────────┼─────────┐
      ▼        ▼         ▼
   tor.exe  dnscrypt   i2pd.exe
      │        │         │
      └── 127.0.0.1:53 ──┘
         local DNS relay
```

- **Transparent mode** uses **ProxyBridge (WinDivert)** to redirect every TCP
  connection to `127.0.0.1:9050` and to block UDP. `tor.exe`,
  `dnscrypt-proxy.exe`, `i2pd.exe` and ProxyBridge itself are exempt to avoid
  loops.
- **Kill switch** saves the original firewall policy and adds *Allow* rules for
  Tor, DNSCrypt, i2pd, ProxyBridge, pluggable transports and the local DNS
  relay. In **proxy mode** the default outbound action is set to **Block**.
  In **transparent mode** the firewall must stay in allow mode (Windows
  Firewall evaluates packets before WinDivert), and ProxyBridge enforces the
  policy instead; a watchdog restores **Block** if ProxyBridge dies.
- **DNS** uses a local relay on `127.0.0.1:53` and `[::1]:53`, because Windows
  cannot specify a port in the adapter DNS settings.
- **LAN and VPN** traffic to private ranges and to `vpn.allow` endpoints stays
  direct, matching the Linux nftables ruleset.
- **ICMP** is blocked in transparent mode, because WinDivert only covers
  TCP/UDP.
- **MAC randomization** is applied per Wi-Fi profile through native `netsh`
  (`randomization=yes`) and restored on disconnect. Ethernet is not modified.

The complete architecture, limitations and troubleshooting guide are in
[`README-WINDOWS.md`](README-WINDOWS.md).

---

## Verify the installation

With the app connected and the status **PROTECTED**, run the read-only audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-windows.ps1
```

It checks the privacy processes, listening ports, system DNS, WinINET proxy,
firewall policy and Entropy Shield rules, the Tor exit (`"IsTor": true`),
transparent routing of an app that ignores the proxy, and DNS resolution through
`127.0.0.1`.

Manual checks:

```powershell
# Through Tor (no proxy configured)
curl.exe -sS https://check.torproject.org/api/ip

# Direct connection must fail (or be redirected) while protected
curl.exe -sS --noproxy "*" --max-time 5 https://example.com
```

In the isolated Tor Browser profile:

- <https://check.torproject.org>
- <https://browserleaks.com/ip>
- <https://dnsleaktest.com>

---

## Security and recovery

- The helper writes a snapshot before touching the firewall, DNS or proxy. If
  it dies, the next run repairs the state.
- **Panic** restores firewall, DNS and proxy immediately.
- **Disconnect** restores the original state and removes all Entropy Shield
  firewall rules.
- If the app and the helper are both gone, run as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-windows.ps1
```

  This executes `Entropy Shield.exe --windows-restore` (installed or `dist\`
  copy), so it does **not** require Python. Details are written to
  `%LOCALAPPDATA%\entropy-shield\restore.log`.

- The portable EXE is **not code-signed**, so Windows SmartScreen may warn.
  Verify the SHA-256 published with each release before running it.

---

## Limitations

- Transparent mode requires ProxyBridge and Administrator. Without it the app
  falls back to **SOCKS proxy mode**: apps that ignore the proxy are blocked by
  the kill switch, but they cannot be forced through Tor.
- Transparent mode is not a Linux *network namespace* sandbox; it is
  process-based redirection with a fail-closed watchdog.
- “Run any app through Tor” covers the selected executable. Child processes with
  a different image name are not matched by the process rule, although they
  inherit the proxy environment variables.
- I2P works in proxy mode. Its transport is direct by default; **Route NTCP2
  via Tor** enables exact Linux parity at the cost of Tor performance.
- MAC randomization is Wi-Fi only; Ethernet is intentionally untouched.
- VPN endpoints must be listed explicitly in `vpn.allow`; there is no automatic
  WireGuard/OpenVPN/Tailscale detection.
- IPv6 is not configured on every network; when present, it is covered by the
  proxy and firewall rules but should be tested explicitly.

---

## Project layout

```text
main.py                 Application entry point
core/windows/           Windows backend (helper, firewall, Tor, DNS, I2P, torify)
core/                   Portable / Linux modules kept from upstream
gui/                    PyQt6 interface, themes and icons
scripts/                Setup, build, install, uninstall, restore and audit
tests/                  Unit tests (including transparent-mode tests)
bin/                    Downloaded binaries (gitignored, placeholder README)
Fonts/                  Optional UI font (see Fonts/README.md)
logos/, screenshots/    Documentation assets
docs/README-LINUX.md    Original upstream Linux documentation
```

Development run and tests:

```powershell
python -m pip install PyQt6
python main.py
python -m unittest discover -s tests -v
```

`tests/test_transparent.py` covers the Windows backend. `tests/test_torify.py`
targets the Linux implementation and is skipped automatically on Windows.

---

## Credits & attribution

### Original project

This software is a **native Windows adaptation** of **Entropy Shield**, created
by **Berk Küçük**:

- Upstream repository: <https://github.com/berk-kucuk/entropy-shield>
- Author: <https://berkkucukk.com>
- Upstream license: MIT — `Copyright (c) 2026 Berk Küçük`

The upstream Linux implementation, architecture and interface design are his
work. This repository adds the Windows backend and packaging while preserving
the original copyright notice and license terms.

Windows adaptation: **Guillermo García Blanco**, 2026.

### Third-party components

| Component | License | Use |
|---|---|---|
| [Tor](https://www.torproject.org/) | BSD-3-Clause | Anonymity network and SOCKS/control ports |
| [dnscrypt-proxy](https://github.com/DNSCrypt/dnscrypt-proxy) | ISC | Encrypted DNS |
| [i2pd](https://github.com/PurpleI2P/i2pd) | BSD-3-Clause | I2P router |
| [ProxyBridge](https://github.com/InterceptSuite/ProxyBridge) | MIT | Transparent per-process routing (WinDivert) |
| [WinDivert](https://reqrypt.org/windivert.html) | LGPL-3.0 / dual | Packet redirection driver used by ProxyBridge |
| [Qt 6](https://www.qt.io/) / [PyQt6](https://riverbankcomputing.com/software/pyqt/) | GPL-3.0 or commercial | GUI toolkit |
| [Lucide](https://lucide.dev) icons | ISC | Interface icons |
| [Simple Icons](https://simpleicons.org) | CC0-1.0 | Tor logo |
| [Press Start 2P](https://github.com/google/fonts/tree/main/ofl/pressstart2p) | SIL OFL 1.1 | Pixel theme display font |

These components are **not** covered by this repository's MIT license. They are
downloaded at setup time or bundled by the build and remain under their own
terms. See `gui/icons/LICENSE-lucide.txt` and
`gui/icons/LICENSE-simple-icons.md`.

> **PyQt6 licensing:** PyQt6 is dual-licensed under **GPL-3.0** or a commercial
> Riverbank license. Distributing a binary that links PyQt6 requires complying
> with the GPL-3.0 (including making the corresponding source available) or
> holding a commercial PyQt license. The MIT license of this repository applies
> to its own source code; it does not override PyQt6's terms. If you need a
> permissive-only distribution, switch the imports to **PySide6** (LGPL-3.0).

### Fonts

The “Pixel” theme ships with **Press Start 2P** by CodeMan38, licensed under
the **SIL Open Font License 1.1** (see
[`Fonts/PressStart2P-OFL.txt`](Fonts/PressStart2P-OFL.txt)). The theme was
originally designed around **Pixeled** by OmegaPC777, but that font uses the
FontStruct Non-Commercial EULA, whose section 2.3 forbids redistribution; it is
therefore **not** included in this repository. If a licensed `Pixeled.ttf` is
present locally it takes priority; otherwise the theme uses Press Start 2P. See
[`Fonts/README.md`](Fonts/README.md).

---

## License

This project is released under the **MIT License**. See [`LICENSE`](LICENSE).

The original copyright notice is preserved:

```text
Copyright (c) 2026 Berk Küçük
Copyright (c) 2026 Guillermo García Blanco (Windows adaptation)
```
