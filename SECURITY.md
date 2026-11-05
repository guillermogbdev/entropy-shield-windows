# Security Policy

Entropy Shield for Windows runs an **elevated helper** that changes the Windows
Firewall, the system DNS and the per-user WinINET proxy, and can launch Tor,
DNSCrypt and I2P. Security reports are taken seriously.

## Supported versions

| Version | Supported |
|---|---|
| 4.3.x-windows | ✅ |
| older builds | ❌ |

## Reporting a vulnerability

**Do not open a public issue for a vulnerability.**

Use GitHub's private vulnerability reporting:

<https://github.com/guillermogbdev/entropy-shield-windows/security/advisories/new>

Include:

- affected version or commit;
- Windows version and whether the persistent helper task is installed;
- steps to reproduce;
- impact (for example: kill-switch bypass, DNS leak, privilege escalation,
  command injection, network left blocked after a crash);
- logs from `%LOCALAPPDATA%\entropy-shield\` with any personal data removed.

You can expect an initial response within **7 days**. Please allow time for a fix
and a coordinated release before public disclosure.

## Scope

Especially relevant areas:

- privilege boundary between the unprivileged GUI and the elevated helper
  (loopback line protocol, per-user token in `daemon.json`);
- kill-switch and transparent-mode bypasses (TCP, UDP/QUIC, WebRTC, IPv6, DNS);
- command injection in the helper protocol, `torify` launcher or PowerShell
  scripts;
- unsafe restore/rollback that leaves the machine without connectivity;
- path traversal in the onion server or browser-profile handling.

Out of scope:

- the fact that the portable EXE is unsigned and triggers SmartScreen;
- vulnerabilities in Tor, DNSCrypt, i2pd, ProxyBridge, WinDivert or Qt/PyQt6
  (report those upstream; we will still update the bundled versions);
- physical access or an already-compromised administrator account;
- the GPL-3.0/commercial licensing of PyQt6 (a legal, not a security, issue).

## Design notes and known limitations

- The helper listens only on `127.0.0.1` and requires a random per-user token.
- Transparent mode depends on ProxyBridge/WinDivert and requires Administrator.
- Transparent mode is **not** a network-namespace sandbox: it is process-based
  redirection with a fail-closed watchdog.
- “Run any app through Tor” covers the selected executable; children with a
  different image name inherit only the proxy environment variables.
- VPN endpoints must be listed explicitly in `vpn.allow`.
- `Pixeled.ttf` is intentionally excluded for licensing reasons.

## Verifying a release

Every release publishes a SHA-256 next to the ZIP. Verify it before running:

```powershell
Get-FileHash .\Entropy-Shield-4.3.0-windows.1.zip -Algorithm SHA256
```

The executable is not code-signed.
