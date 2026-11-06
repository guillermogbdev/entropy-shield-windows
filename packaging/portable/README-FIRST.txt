Entropy Shield for Windows - first run
======================================

Requirements
- Windows 10 or 11, 64-bit.
- An Administrator account (UAC is needed for the privileged helper).
- Internet access for the Tor network.

Quick start (portable)
1. Extract the whole ZIP to a normal folder. Do not run it from inside the ZIP.
2. If Windows marked the files as downloaded, run UNBLOCK-FILES.bat once.
   (Alternatively: right-click the ZIP -> Properties -> Unblock before extracting.)
3. Run "Start Entropy Shield.bat" (or Entropy Shield.exe).
4. SmartScreen: click "More info" -> "Run anyway". The EXE is not code-signed;
   verify the SHA-256 published in the GitHub release.
5. Press Connect and accept the UAC prompt. Transparent Tor needs Administrator.
6. Verify with https://check.torproject.org (green) or:
     curl.exe -sS https://check.torproject.org/api/ip

Everything is bundled. Tor, DNSCrypt, i2pd and ProxyBridge/WinDivert live in
bin\. No Python, no setup script and no extra downloads are required.

Daily use (recommended)
- Run "Install to Program Files.bat" (UAC). It copies the app to
  %ProgramFiles%\Entropy Shield, creates a Start Menu shortcut and registers
  the Entropy Shield Helper logon task, so Connect no longer asks for UAC.
- Installed under Program Files, the executable is read-only for normal users;
  the elevated helper cannot be replaced from a user-writable folder.

If an app loses its connection
- Transparent mode sends every TCP connection through Tor. Some endpoints
  (campus/corporate LLM APIs, VPN servers, internal services) must stay direct.
- Open Settings -> Routing and add the app's process as Direct, or add the
  destination IP/CIDR to Direct endpoints.
- The activity log reports "Tor refused <ip:port>" with the same advice.
- scripts\add-direct.ps1 -ListRefused lists endpoints Tor refused.

Troubleshooting
- Logs: %LOCALAPPDATA%\entropy-shield\ (daemon.log, proxybridge.log).
- Emergency network restore (Administrator):
    powershell -ExecutionPolicy Bypass -File scripts\restore-windows.ps1
- Read-only audit while connected:
    powershell -ExecutionPolicy Bypass -File scripts\check-windows.ps1
- Windows Defender may ask about WinDivert (used for transparent Tor). Allow it.

Virtual machines
- Use NAT or bridged networking. Tor needs outbound TCP; the VM must have
  Internet access before Connect.
- Give the VM at least 4 GB RAM and 2 vCPUs for a comfortable first start.
- Take a snapshot before the first Connect if you want a quick rollback.

License and credits
- MIT License. Original project: https://github.com/berk-kucuk/entropy-shield
- Windows adaptation: Guillermo Garcia Blanco, 2026.
- Third-party: Tor (BSD-3-Clause), dnscrypt-proxy (ISC), i2pd (BSD-3-Clause),
  ProxyBridge (MIT), WinDivert (LGPL-3.0), Qt/PyQt6 (GPL-3.0 or commercial),
  Press Start 2P (SIL OFL 1.1). See LICENSE and the bundled license files.
