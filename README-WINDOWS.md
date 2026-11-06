# Entropy Shield — Windows

This is a native Windows 10/11 adaptation of the original Linux project. The
interface is the same (PyQt6), but the privileged backend has been rewritten
because Windows does not have systemd, nftables, `iptables` or *network
namespaces*.

> Important: Windows has no `nftables` and no *network namespaces*.
> Transparent mode is implemented with **ProxyBridge/WinDivert**: it redirects
> all TCP from any process to Tor and blocks UDP. It requires Administrator. If
> ProxyBridge is not installed or UAC is denied, the app still works in
> **SOCKS proxy mode** and the *kill switch* prevents direct leaks.

---

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

---

## Requirements

- Windows 10 or 11, 64-bit.
- Python 3.10 or newer (tested with 3.14).
- PyQt6 (installed by the script).
- The Tor, DNSCrypt and i2pd binaries. The setup script downloads them.
- Administrator permission **only for the helper**. If you install with
  `install-windows.ps1`, a logon task starts it elevated without UAC; if you use
  the portable build, the first Connect prompts for UAC. The ProxyBridge
  installer may also prompt for UAC to register its service.

---

## Quick installation

> **Using the release ZIP?** You do not need this section. The portable package
> already contains Tor, DNSCrypt, i2pd and ProxyBridge; run `Entropy Shield.exe`
> and follow `README-FIRST.txt`.

Open PowerShell in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

The script:

1. checks Python;
2. installs `PyQt6`;
3. downloads the official **Tor Expert Bundle**, **dnscrypt-proxy** and
   **i2pd** into `bin\`;
4. installs **ProxyBridge** in `%LOCALAPPDATA%\entropy-shield\proxybridge`
   for transparent mode (its installer may prompt for UAC to create the
   service);
5. leaves everything ready to run.

Then:

```bat
run-windows.bat
```

To start directly in the tray, without a console, use
`run-windows-tray.vbs`.

A portable executable can also be built:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

The result is `dist\Entropy Shield\Entropy Shield.exe`, with `bin\` copied next
to it so it can find Tor, DNSCrypt and i2pd.

If you installed with `scripts\install-windows.ps1`, the **Entropy Shield
Helper** task is registered and the elevated helper starts at logon: you will
not see UAC when connecting. Without that task (for example, running from
`dist\`), the first **Connect** prompts for UAC. You can register it manually:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-helper-task.ps1
```

The helper still listens only on `127.0.0.1` and requires the random token from
`%LOCALAPPDATA%\entropy-shield\daemon.json`. The GUI and browsers still run as a
normal user.

The window starts maximized on small screens or with high Windows scaling
(125–200 %). You can maximize/restore with the title-bar button, by
double-clicking the title bar, or with **F11**. The content scrolls with the
mouse wheel when it does not fit.

### If you already have Tor Browser

The program also searches automatically:

```text
%ProgramFiles%\Tor Browser\Browser\TorBrowser\Tor\tor.exe
%LOCALAPPDATA%\Programs\Tor Browser\...\tor.exe
%USERPROFILE%\Desktop\Tor Browser\...\tor.exe
```

You can set paths manually in `%APPDATA%\entropy-shield\config.json`:

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
- **Onion Server**: built-in HTTP server + `HiddenServiceDir` in the torrc.
- **Transparent mode**: ProxyBridge (WinDivert) redirects TCP from every
  process to `127.0.0.1:9050`. `tor.exe`, `dnscrypt-proxy.exe`, `i2pd.exe` and
  ProxyBridge itself are exempt to avoid loops. UDP is blocked. *Per-app
  routing* rules are translated by process name.
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

---

## Important limitations

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
  automatic WireGuard/OpenVPN/Tailscale detection as on Linux; if you use a
  VPN, add its server IP/CIDR to that list.
- **DNS**: DNSCrypt over Tor can be slow while dnscrypt-proxy probes its
  resolvers (tens of seconds of RTT under load). With I2P also routed through
  Tor, the first queries may time out; a retry usually works. This is inherited
  from the Linux design (i2pd NTCP2 via Tor, SSU2 off).
- Programs that use **WinHTTP** (some services) do not read the WinINET proxy.
  The firewall still blocks their direct egress.
- The **Onion Server** serves files as the user running the GUI. Do not publish
  your home folder; the app rejects `C:\Users\...` and system paths.

---

## Security and recovery

- The helper writes a snapshot before touching the firewall, DNS or proxy. If
  the process dies, the next run repairs the state.
- The optional **Entropy Shield Helper** task keeps an elevated helper running
  in the background from logon (a lightweight equivalent of the systemd
  daemon). It listens only on loopback, uses a per-user token, and is removed by
  `uninstall-windows.ps1` or with
  `Unregister-ScheduledTask -TaskName 'Entropy Shield Helper'`.
- **Panic** restores firewall, DNS and proxy immediately.
- If something remains blocked, run as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-windows.ps1
```

  The script executes `Entropy Shield.exe --windows-restore` (the installed copy
  or the one in `dist\`), so it **does not require Python**. If restoration
  fails, it keeps the snapshot and writes the details to
  `%LOCALAPPDATA%\entropy-shield\restore.log`; run it again after closing the
  application (or reboot) to retry.

- Always verify hashes/signatures of downloaded binaries. The setup script uses
  HTTPS and official sources, but it does not verify GPG signatures
  automatically.
- In this adaptation, `tor.exe`, `dnscrypt-proxy.exe` and `i2pd.exe` are
  launched from the elevated helper and inherit its Administrator token. This
  simplifies the lifecycle next to the firewall, but it differs from Linux
  (where Tor runs as an unprivileged user). If you need least privilege, use Tor
  Browser and the official clients separately.
- **Install under Program Files for daily use.** If you run the `.exe` from a
  user-writable folder (Downloads, Desktop), any local process could modify the
  code before you accept the helper's UAC prompt. Installed under Program Files,
  the executable and the helper are read-only for the user:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

  The installer creates the Start Menu shortcut. To uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ps1
```

  Add `-RemoveData` if you also want to delete configuration, the Tor cache and
  the onion service keys.

---

## Verification

With the app connected and the **PROTECTED** status, run the read-only audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-windows.ps1
```

It automatically checks:

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

You can also test from the app's **Tor Browser** button:

- `https://check.torproject.org`
- `https://browserleaks.com/ip`
- `https://dnsleaktest.com`

Remember: with **Transparent Tor** enabled (ProxyBridge + Administrator), any
application goes through Tor even if it ignores the proxy. Without it, Tor is a
local proxy and the kill switch only blocks direct egress. Transparent mode
appears in the log as:

```text
[TRANSPARENT] Active: every TCP connection is routed through Tor; UDP and QUIC/WebRTC are blocked.
```

To check it without configuring a proxy:

```powershell
curl.exe -sS https://check.torproject.org/api/ip
```

It must return `"IsTor": true`. A direct connection (`--noproxy '*'`) to a
non-loopback service must fail or go through Tor, never show your real IP.

If you kill `ProxyBridge_CLI.exe` while connected, the watchdog sets the
firewall to `Block` within 10 seconds and direct egress fails again. This is the
fail-closed guarantee of transparent mode.

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
version and does not need Python. You can also reboot: the helper saves the
snapshot and repairs it at startup. Details of the last repair are written to
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

Transparent mode routes every TCP connection through Tor. Some applications use
endpoints that Tor cannot reach (campus/corporate LLM APIs, VPN servers,
internal services) or long-lived sessions that reset when the route changes.
Check `%LOCALAPPDATA%\entropy-shield\proxybridge.log` for
`proxy replied 0x05`. Then open **Settings → Routing** and add the app's
process as **Direct**, or add the endpoint IP/CIDR to **Direct endpoints**
(`vpn.allow`). The rest of the system keeps using Tor.

**The Onion Server does not start / port 8080 is reserved**
Windows may reserve port 8080 (Hyper-V, WSL, another service). If the configured
port cannot be opened, the app automatically chooses another free port, updates
the torrc `HiddenServicePort` and reports it in the log:

```text
[ONION] Port 8080 is unavailable (...); using 56510 instead.
```

The `.onion` keeps working on the alternative port.

---

## Development

```powershell
python -m pip install PyQt6
python main.py
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
- `scripts/install-helper-task.ps1` — persistent helper at logon.

### Tests

```powershell
python -m unittest discover -s tests -v
```

`tests/test_transparent.py` covers the Windows transparent-mode profile.
`tests/test_torify.py` exercises the Linux implementation (`fcntl`, network
namespaces) and is skipped automatically on Windows.

The Linux modules have not been removed: the same tree still works on Linux with
systemd, nftables and the original daemon. See
[`docs/README-LINUX.md`](docs/README-LINUX.md).
