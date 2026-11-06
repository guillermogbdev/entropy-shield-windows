<div align="center">

<img src="logos/oled.png" alt="Entropy Shield" width="110" />

# Entropy Shield — Windows

### Native Windows 10/11 port of the Entropy Shield privacy stack

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?style=flat-square&logo=windows&logoColor=white)](#requirements)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-41CD52?style=flat-square&logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Windows build](https://github.com/guillermogbdev/entropy-shield-windows/actions/workflows/windows.yml/badge.svg?branch=main)](https://github.com/guillermogbdev/entropy-shield-windows/actions/workflows/windows.yml)

**One GUI to control Tor, DNSCrypt, I2P and onion services — with transparent,
system-wide Tor routing on Windows.**

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
> `nftables`, `iptables` or Linux *network namespaces*). The Linux modules are
> still in the tree; their original documentation is kept in
> [`docs/UPSTREAM-LINUX.md`](docs/UPSTREAM-LINUX.md).
>
> Original work: <https://github.com/berk-kucuk/entropy-shield>  
> Upstream author: <https://berkkucukk.com>

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

## What works

| Feature | Status on Windows |
|---|---|
| GUI, themes, system tray | ✅ Complete |
| Tor (SOCKS + ControlPort + DNSPort) | ✅ Complete |
| Circuit renewal (`NEWNYM`) | ✅ Complete |
| DNSCrypt-proxy | ✅ Complete, with system DNS redirected to a local relay |
| I2P (i2pd) | ✅ HTTP/SOCKS proxy; direct transport by default (optional NTCP2 via Tor) |
| Onion Server (`.onion`) | ✅ With built-in HTTP server |
| Kill switch | ✅ Firewall in `Block` (proxy mode) / ProxyBridge + watchdog (transparent mode) |
| DNS, proxy and firewall restoration | ✅ On Disconnect, Panic or the recovery script |
| Isolated Tor / I2P browser | ✅ Separate Firefox/Edge/Chrome/Brave profiles |
| IP Check / Leak Test | ✅ Adapted to Windows |
| Auto-reconnect / auto-connect | ✅ |
| Start with Windows | ✅ HKCU `Run` key |
| System-wide transparent proxy | ✅ With ProxyBridge/WinDivert (requires Administrator) |
| UDP blocking (QUIC/WebRTC/direct DNS) | ✅ In transparent mode |
| Per-app routing | ✅ By process name in transparent mode |
| Direct LAN (router, NAS, printers) | ✅ Direct TCP/UDP, same as nftables |
| ICMP/ping blocking | ✅ In transparent mode |
| VPN exemption | ✅ Explicit via `vpn.allow` |
| MAC randomization | ✅ Wi-Fi (native per-profile setting); Ethernet not supported |
| “Run any app through Tor” | ✅ Transparent per process (helper + ProxyBridge); browsers use an isolated profile |
| Network namespaces / fail-closed “Run any app” | ✅ Approximated: per-process ProxyBridge + watchdog; not a sandbox |

## Requirements

| Component | Requirement |
|---|---|
| OS | Windows 10 or 11, 64-bit |
| Python | 3.10 or newer (tested with 3.14) — **not needed for the release ZIP** |
| GUI | PyQt6 6.4+ (installed by the setup script or bundled in the ZIP) |
| Privacy binaries | Tor Expert Bundle, dnscrypt-proxy and i2pd (bundled in the ZIP) |
| Privileges | Administrator **only** for the elevated helper; the GUI runs as a normal user |

The app is **portable**: it does not need an installer, but installing it under
`Program Files` is recommended for daily use (see below).

---

## Portable release (fresh Windows VM)

Download the ZIP from
[Releases](https://github.com/guillermogbdev/entropy-shield-windows/releases),
then:

1. **Extract the whole ZIP** to a normal folder. Do not run it from inside the
   ZIP viewer.
2. Run `UNBLOCK-FILES.bat` once if Windows marked the files as downloaded
   (or right-click the ZIP → **Properties** → **Unblock** before extracting).
3. Run `Start Entropy Shield.bat` (or `Entropy Shield.exe`).
4. SmartScreen: **More info → Run anyway**. The EXE is not code-signed; verify
   the SHA-256 published with the release.
5. Press **Connect** and accept the UAC prompt.
6. Verify with <https://check.torproject.org> (green) or:

   ```powershell
   curl.exe -sS https://check.torproject.org/api/ip
   # Expected: "IsTor": true
   ```

Tor, DNSCrypt, i2pd and ProxyBridge/WinDivert are bundled, so **no Python and
no setup script are required**. See `README-FIRST.txt` inside the ZIP for the
same steps plus VM and network notes.

### UAC prompts you will see

| Moment | Prompts |
|---|---|
| `Install to Program Files.bat` | 1 |
| Sign-in, Connect, closing/reopening the app | 0 |
| First Connect on a portable copy without the logon task | 1 |

## Install for daily use (recommended)

From the extracted ZIP, run `Install to Program Files.bat`. From a source
checkout, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

Either way the app is copied to `%ProgramFiles%\Entropy Shield`, a Start Menu
shortcut is created and the **Entropy Shield Helper** logon task is registered.
The helper starts elevated at logon, so pressing **Connect** does not prompt for
UAC.

```powershell
# Register the helper task manually (optional)
powershell -ExecutionPolicy Bypass -File .\scripts\install-helper-task.ps1

# Uninstall (add -RemoveData to delete configuration, Tor cache and onion keys)
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ps1
```

> **Security note:** install under `Program Files`. If you run the EXE from a
> user-writable folder (Desktop, Downloads), a local process could modify the
> binary before you approve the helper's UAC prompt. Under Program Files the
> executable and the helper are read-only for normal users.

## Build from source

Open PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

The script checks Python, installs PyQt6, downloads the official Tor Expert
Bundle, dnscrypt-proxy and i2pd into `bin\`, and installs ProxyBridge in
`%LOCALAPPDATA%\entropy-shield\proxybridge` for transparent mode. Some steps may
ask for UAC (ProxyBridge service registration).

Run the app:

```bat
run-windows.bat
```

To start directly in the system tray without a console window:

```bat
wscript run-windows-tray.vbs
```

Build the portable executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

Output: `dist\Entropy Shield\Entropy Shield.exe`, with `bin\` and the
documentation copied next to it.

### If you already have Tor Browser

The program searches these locations automatically:

```text
%ProgramFiles%\Tor Browser\Browser\TorBrowser\Tor\tor.exe
%LOCALAPPDATA%\Programs\Tor Browser\...\tor.exe
%USERPROFILE%\Desktop\Tor Browser\...\tor.exe
```

You can also set explicit paths in `%APPDATA%\entropy-shield\config.json`:

```json
{
  "binaries": {
    "tor": "C:/path/to/tor.exe",
    "dnscrypt_proxy": "C:/path/to/dnscrypt-proxy.exe",
    "i2pd": "C:/path/to/i2pd.exe"
  }
}
```

Or with environment variables:

```powershell
$env:ENTROPY_SHIELD_TOR = "C:\path\to\tor.exe"
$env:ENTROPY_SHIELD_DNSCRYPT_PROXY = "C:\path\to\dnscrypt-proxy.exe"
$env:ENTROPY_SHIELD_I2PD = "C:\path\to\i2pd.exe"
```

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

- **Tor** is configured with `SocksPort`, `ControlPort` and `DNSPort`.
- **DNS**: Windows does not allow specifying a port in the adapter DNS
  settings, so a local relay listens on `127.0.0.1:53` (and `[::1]:53`) and
  forwards to Tor's `DNSPort` or to the dnscrypt-proxy port.
- **System proxy**: the per-user WinINET proxy is enabled
  (`socks=127.0.0.1:9050` or `http=127.0.0.1:4444`).
- **Kill switch**: the original firewall policy is saved and *Allow* rules are
  added for `tor.exe`, `dnscrypt-proxy.exe`, `i2pd.exe`, ProxyBridge, pluggable
  transports and the local DNS/proxy ports. In **proxy mode** the default
  outbound action is set to **Block**; everything is restored on disconnect.
  In **transparent mode** `Block` cannot be used: Windows Firewall evaluates
  packets before WinDivert, so non-allowed applications would never reach
  ProxyBridge. ProxyBridge enforces the full policy (all TCP → Tor, all UDP
  blocked) and a watchdog checks every 5 s that it is still alive; if it dies,
  the firewall is set back to `Block`. A TCP rule for **System** (PID 4) is also
  added for that case, because WinDivert reinjects DIRECT traffic with that
  identity.
- **Transparent mode**: ProxyBridge (WinDivert) redirects TCP from every
  process to `127.0.0.1:9050`. `tor.exe`, `dnscrypt-proxy.exe`, `i2pd.exe` and
  ProxyBridge itself are exempt to avoid loops. UDP is blocked. *Per-app
  routing* rules are translated by process name.
- **Onion Server**: built-in HTTP server + `HiddenServiceDir` in the torrc.
- **I2P**: uses direct transport (NTCP2/SSU2) by default, which is stable and
  does not compete with Tor; I2P already provides its own anonymity. The
  **Route NTCP2 via Tor** setting replicates the Linux behaviour (i2pd through
  Tor), but most I2P peers are not reachable through Tor exits and it can
  congest Tor/DNS. Enable it only if you need to hide I2P usage from your ISP.
- **Run any app through Tor**: the elevated helper starts a ProxyBridge instance
  with a profile that only redirects the chosen executable; the rest of the
  system stays DIRECT. A thread watches ProxyBridge and terminates the app if it
  dies. For browsers, an isolated profile with an explicit SOCKS proxy is used
  as well.
- **LAN and VPN**: traffic to private networks (10/8, 172.16/12, 192.168/16,
  link-local, multicast) goes direct, as in the Linux nftables ruleset.
  `vpn.allow` endpoints are also exempt from the proxy and the kill switch.
- **ICMP**: in transparent mode, firewall rules block ICMPv4/ICMPv6 because
  WinDivert only covers TCP/UDP.
- **MAC**: on Wi-Fi, the WLAN profile's `MAC Randomization` is enabled
  (`netsh wlan … randomization=yes`), which Windows applies natively on
  reconnect; it is restored on disconnect. There is no safe API for Ethernet.
- **Tray**: native `QSystemTrayIcon` (no helper process as on Linux).

## Background helper

Installing with `Install to Program Files.bat` (or `install-windows.ps1`)
registers the **Entropy Shield Helper** logon task. The helper is the elevated
part that touches the firewall, DNS, proxy settings and Tor/ProxyBridge; the GUI
itself never runs with Administrator rights.

It keeps running in the background on purpose:

- it is what lets later **Connect** actions skip the UAC prompt, even after you
  close and reopen the app;
- it keeps the firewall/DNS state consistent between sessions and repairs a
  previous crash on the next start;
- measured footprint on an idle Windows 11 machine: **~19 MB private memory,
  ~33 MB working set, one thread, 0 % CPU**. It listens only on `127.0.0.1` and
  requires the random per-user token in
  `%LOCALAPPDATA%\entropy-shield\daemon.json`.

For comparison, the GUI uses around 100 MB, so the helper is the small part. It
is stopped by `scripts\restore-windows.ps1`, by `uninstall-windows.ps1`, and at
sign-out. To stop it manually:

```powershell
Stop-ScheduledTask -TaskName 'Entropy Shield Helper'
```

---

## Verify the installation

With the app connected and the status **PROTECTED**, run the read-only audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-windows.ps1
```

It checks:

- Tor, DNSCrypt and i2pd processes;
- local ports (`9050`, `9051`, `5300`, `5380`, `4444`, `4447`, `53`);
- system DNS pointing to `127.0.0.1`;
- the WinINET proxy;
- the firewall policy for the active mode (`Block` in proxy mode; allow mode
  with ProxyBridge in transparent mode) and the rules in the `Entropy Shield`
  group;
- the Tor exit IP (`"IsTor": true`);
- in transparent mode, that a connection without a proxy also exits through
  Tor;
- in proxy mode, that a direct connection without a proxy fails while
  protected;
- that ICMP (ping) is blocked in transparent mode;
- that LAN traffic (router/NAS) remains direct and does not go through Tor.

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

Remember: with **Transparent Tor** enabled (ProxyBridge + Administrator), any
application goes through Tor even if it ignores the proxy. Without it, Tor is a
local proxy and the kill switch only blocks direct egress. Transparent mode
appears in the log as:

```text
[TRANSPARENT] Active: every TCP connection is routed through Tor; UDP and QUIC/WebRTC are blocked.
```

If you kill `ProxyBridge_CLI.exe` while connected, the watchdog sets the
firewall to `Block` within 10 seconds and direct egress fails again. This is the
fail-closed guarantee of transparent mode.

---

## Security and recovery

- The helper writes a snapshot before touching the firewall, DNS or proxy. If
  the process dies, the next run repairs the state.
- **Panic** restores firewall, DNS and proxy immediately.
- **If the network drops while connected**, the watchdog checks Tor every 20 s,
  shows **Network lost - protection is blocking traffic**, restores firewall,
  DNS and proxy, and retries the connection up to 10 times. You can trigger the
  same recovery at once by clicking the notification, using **Panic**, or
  running the **Restore Entropy Shield network** Start Menu shortcut (installed
  with the app). That shortcut launches the elevated restore even if the GUI
  will not open.
- **After Connect, Tor is verified with a real request.** Bootstrap alone is not
  proof that exits are reachable. If Tor cannot complete a SOCKS request within
  ~15 s, the app disconnects and restores the normal connection instead of
  leaving you with a dead system proxy.
- **Disconnect** restores the original state and removes all Entropy Shield
  firewall rules.
- If something remains blocked, run as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-windows.ps1
```

  The script executes `Entropy Shield.exe --windows-restore` (the installed copy
  or the one in `dist\`), so it **does not require Python**. If restoration
  fails, it keeps the snapshot and writes the details to
  `%LOCALAPPDATA%\entropy-shield\restore.log`; run it again after closing the
  application (or reboot) to retry.

- The portable EXE is **not code-signed**, so Windows SmartScreen may warn.
  Verify the SHA-256 published with each release before running it.
- Always verify hashes/signatures of downloaded binaries. The setup script uses
  HTTPS and official sources, but it does not verify GPG signatures
  automatically.
- In this adaptation, `tor.exe`, `dnscrypt-proxy.exe` and `i2pd.exe` are
  launched from the elevated helper and inherit its Administrator token. This
  simplifies the lifecycle next to the firewall, but it differs from Linux
  (where Tor runs as an unprivileged user). If you need least privilege, use Tor
  Browser and the official clients separately.
- The helper listens only on loopback, requires the random per-user token in
  `%LOCALAPPDATA%\entropy-shield\daemon.json`, and is removed by
  `uninstall-windows.ps1` or with
  `Unregister-ScheduledTask -TaskName 'Entropy Shield Helper'`.

---

## If an app loses its connection

Transparent mode sends every TCP connection through Tor. Some apps use
endpoints that Tor cannot reach (campus or corporate LLM APIs, VPN servers,
internal services) or long-lived sessions that reset when the route changes.
If an app disconnects after **Connect**:

1. Open **Settings → Routing** and add the app's process (for example
   `opencode-cli.exe`) as **Direct**.
2. Or put the endpoint IP/CIDR in **Settings → Routing → Direct endpoints**
   (stored in `vpn.allow`).
3. Check `%LOCALAPPDATA%\entropy-shield\proxybridge.log` for
   `proxy replied 0x05`; the activity log reports the refused endpoint with the
   same suggestion.

These exemptions are deliberate: that traffic stays direct while the rest of
the system continues to use Tor.

## Network compatibility

The app does **not** need inbound ports and leaves the Windows Firewall in its
normal allow mode. When something fails on a particular network, the cause is
usually the **network's own firewall or admission policy**, not Windows.

| Network | What can fail | What to do |
|---|---|---|
| **Campus / enterprise Wi-Fi (eduroam, 802.1X)** | Many universities block or throttle Tor; certificate/MAC-based admission can also reject the connection. | Try **Settings → Tor → Bridges** (`obfs4` or `meek-azure`). If Tor bootstraps but a campus service fails, add that service to **Direct endpoints**. |
| **Captive portals** (hotels, airports, cafes) | Tor cannot bootstrap until the portal login is complete, and the kill switch blocks the portal redirect. | Sign in to the portal in a browser **before** pressing Connect. If it reappears, Disconnect, sign in, Connect again. |
| **Networks that only allow 80/443** | Tor's fallback usually works on 443; some firewalls still block it. | Enable obfs4/meek bridges and retry. |
| **Guest Wi-Fi with client isolation** | LAN features (Onion Server, local sharing) cannot be reached by other devices. Tor itself works. | Nothing to fix for Tor; use a non-isolated network for LAN features. |
| **Corporate proxy / TLS inspection** | Proxy rules or certificate inspection can break Tor's TLS. | Use bridges, or a different network. |
| **VPN on the same machine** | The VPN client's kill switch/firewall can block Tor, or Tor can try to reach the VPN server through itself. | Follow the VPN checklist below. |

### VPN checklist

1. Find the VPN server's public IP (or CIDR) and add it in
   **Settings → Routing → Direct endpoints** (`vpn.allow`). That keeps the
   tunnel endpoint out of Tor and out of the kill switch.
2. If the VPN client has its own firewall/kill switch, allow the Tor executable
   (`bin\tor\tor\tor.exe`) and `ProxyBridge_CLI.exe` there.
3. Usual order: **VPN first, then Entropy Shield**. If Tor then fails to
   bootstrap, try the reverse.
4. In a VM, NAT networking passes the host VPN through automatically; nothing
   extra is needed inside the guest.
5. There is **no automatic** WireGuard/OpenVPN/Tailscale detection: endpoints
   are always explicit.

### eduroam in practice

eduroam is usually reachable; the problem is the institution's outbound policy.

- Tor stuck at “Bootstrapping” for minutes: the network is probably filtering
  Tor. Enable **obfs4** bridges in Settings → Tor.
- Wi-Fi authentication fails after enabling MAC randomization: turn
  randomization off for that network (eduroam uses 802.1X identities, and some
  deployments also pin the MAC address).
- A campus API or LLM endpoint resets: add it to **Direct endpoints**. The
  activity log reports `Tor refused <ip:port>` for the refused destination.
- The portal asks you to log in again after Connect: Disconnect first, sign in,
  then Connect. The kill switch blocks direct traffic while connected by design.

---

## Troubleshooting

**“tor.exe was not found”**
Run `scripts\setup-windows.ps1` or install Tor Browser. Check
`bin\tor\tor\tor.exe`.

**“Administrator permission was not granted”**
The helper needs elevation for the firewall and DNS. Accept the prompt. If you
installed the logon task it should not appear; if it does, register it with
`scripts\install-helper-task.ps1`. If your machine blocks UAC, run the app from
an account with the required permissions.

**No Internet after closing the app**
Use `scripts\restore-windows.ps1` as Administrator; it works with the installed
version and does not need Python. You can also double-click **Restore Entropy
Shield network** in the Start Menu, or reboot: the helper saves the snapshot and
repairs it at startup. Details of the last repair are written to
`%LOCALAPPDATA%\entropy-shield\restore.log`.

**DNS does not resolve**
Check that the local relay is listening on `127.0.0.1:53`. Another service (for
example, a local DNS server) may be using that port. Stop that service or change
the network configuration.

**The browser does not use Tor**
The browser buttons create a new profile with a proxy. If you open your normal
browser, it keeps using the system configuration and the kill switch blocks its
direct egress. Close all browser windows before using the isolated profile.

**An app loses its connection when I connect**
See [If an app loses its connection](#if-an-app-loses-its-connection).

**The shortcut seems dead / the app does not open**
While a connection is active, closing the window hides the app in the
notification area so Tor and the kill switch keep running; launching the
shortcut again restores the window, as does clicking the tray icon. When the app
is disconnected, the X button **quits** (and the tray menu's **Quit** always
exits, disconnecting first). The privileged helper installed by the logon task
keeps running after a quit, so the next **Connect** does not ask for UAC again.
No reboot is needed.

**The Onion Server does not start / port 8080 is reserved**
Windows may reserve port 8080 (Hyper-V, WSL, another service). If the configured
port cannot be opened, the app automatically chooses another free port, updates
the torrc `HiddenServicePort` and reports it in the log:

```text
[ONION] Port 8080 is unavailable (...); using 56510 instead.
```

The `.onion` keeps working on the alternative port.

---

## Limitations

- **Transparent mode is optional.** If ProxyBridge is installed and the helper
  runs elevated, all TCP goes through Tor even if the application ignores the
  proxy, and UDP is blocked. Otherwise, applications that ignore the proxy
  cannot be forced through Tor: the kill switch prevents the leak, but they lose
  connectivity.
- **`System` exception in the kill switch.** WinDivert reinjects DIRECT traffic
  as PID 4 (`System`). When the firewall returns to `Block` (proxy mode,
  fallback after a ProxyBridge failure, or watchdog) TCP from `System` is
  allowed so Tor is not blocked. This is not a practical leak: ProxyBridge
  still forces application TCP through Tor and blocks UDP; only packets it
  decides to send DIRECT (Tor, DNSCrypt, I2P and explicit rules) use that
  exception.
- **“Run any app through Tor”** on Windows does not use a *network namespace*.
  The elevated helper starts a ProxyBridge instance that redirects only that
  executable's TCP to Tor and blocks its public UDP; if ProxyBridge dies, the
  launcher terminates the app to avoid leaking. Browsers still use an isolated
  profile with an explicit proxy. Child processes with a different image name
  are not covered by the process rule, although they inherit the proxy
  environment variables.
- **I2P** works in proxy mode (HTTP 4444 / SOCKS 4447), without transparent
  redirection. Its transport is direct by default; enable **Route NTCP2 via
  Tor** for exact Linux parity, assuming Tor may become slow or unstable.
- **Per-app routing** works by process name in transparent mode.
- **MAC randomization** works on Wi-Fi through the native WLAN profile setting.
  Ethernet is left untouched (there is no reliable API without restarting the
  adapter and risking connectivity).
- **VPN**: explicit endpoints in `vpn.allow` are supported. There is no
  automatic WireGuard/OpenVPN/Tailscale detection; see the
  [VPN checklist](#vpn-checklist).
- **DNS**: DNSCrypt over Tor can be slow while dnscrypt-proxy probes its
  resolvers (tens of seconds of RTT under load). With I2P also routed through
  Tor, the first queries may time out; a retry usually works.
- Programs that use **WinHTTP** (some services) do not read the WinINET proxy.
  The firewall still blocks their direct egress.
- The **Onion Server** serves files as the user running the GUI. Do not publish
  your home folder; the app rejects `C:\Users\...` and system paths.
- **IPv6** is not configured on every network; when present, it is covered by
  the proxy and firewall rules but should be tested explicitly.

### Intentionally not implemented (risk trade-offs)

These features exist in the Linux version or were considered for Windows, but
were left out on purpose because the Windows implementation would add more risk
than value:

- **Ethernet MAC randomization** — there is no reliable API that changes the
  MAC without restarting the adapter, and a failed change can leave the machine
  offline. Only Wi-Fi profiles are touched.
- **Automatic VPN detection (WireGuard/OpenVPN/Tailscale)** — guessing tunnel
  endpoints can produce false negatives and leak traffic. VPN servers must be
  listed explicitly in `vpn.allow`.
- **Network-namespace sandbox for “Run any app through Tor”** — Windows has no
  equivalent. The port uses a scoped ProxyBridge instance plus a fail-closed
  monitor; it is process redirection, not an isolated namespace.
- **Transparent I2P redirection** — I2P stays in HTTP/SOCKS proxy mode. Forcing
  i2pd transport through Tor can congest Tor and break connectivity, so
  “Route NTCP2 via Tor” is opt-in.
- **Always-on Windows service for the privileged backend** — a system service
  would run with higher privilege and a larger attack surface. The port uses a
  per-user logon task with a loopback-only helper and a random token.
- **Automatic code signing** — requires a paid CA certificate and identity
  verification. Releases publish a SHA-256 instead and remain unsigned.
- **IPv6 validation on every network** — IPv6 is covered by the proxy and
  firewall rules, but it was not validated on a network with global IPv6 in
  this build. Test it explicitly if your ISP provides IPv6.

---

## Development

```powershell
python -m pip install PyQt6
python main.py
python -m unittest discover -s tests -v
```

The Windows code lives in `core\windows\`:

- `daemon_win.py` — elevated helper and line protocol.
- `connection.py` — layer orchestration.
- `tor.py`, `dnscrypt.py`, `i2p.py`, `onion_server.py` — services.
- `firewall.py` — kill switch.
- `transparent.py` — ProxyBridge/WinDivert (transparent mode).
- `netconfig.py` — DNS and WinINET proxy.
- `dns_forwarder.py` — local DNS relay.
- `client.py` — helper client.
- `browser.py`, `torify.py` — browsers and “Run through Tor”.
- `singleton.py`, `close_policy.py`-adjacent process/UI helpers.

`tests/test_transparent.py` covers the Windows transparent-mode profile.
`tests/test_singleton.py` covers the single-instance guard and window
activation. `tests/test_close_policy.py` covers the X-button policy.
`tests/test_helper_persistence.py` covers the persistent helper. `test_torify.py`
targets the Linux implementation and is skipped automatically on Windows.

### Project layout

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
docs/UPSTREAM-LINUX.md  Original upstream Linux documentation
```

The Linux modules have not been removed: the same tree still works on Linux with
systemd, nftables and the original daemon. See
[`docs/UPSTREAM-LINUX.md`](docs/UPSTREAM-LINUX.md).

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
