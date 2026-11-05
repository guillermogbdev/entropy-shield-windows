#requires -Version 5.1
<#
.SYNOPSIS
    Read-only audit of the Windows privacy stack.

.DESCRIPTION
    Shows whether Tor/DNSCrypt/i2pd are running, which ports are listening,
    what DNS and proxy Windows is using, whether the firewall kill switch is
    active, and whether traffic really goes through Tor.

    Run it while Entropy Shield says PROTECTED.  It does not change anything.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
function Heading($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok($t)      { Write-Host "  [OK]   $t" -ForegroundColor Green }
function Warn($t)    { Write-Host "  [WARN] $t" -ForegroundColor Yellow }
function Bad($t)     { Write-Host "  [FAIL] $t" -ForegroundColor Red }
function Info($t)    { Write-Host "         $t" -ForegroundColor Gray }

Heading "Privacy processes"
foreach ($name in 'tor.exe','dnscrypt-proxy.exe','i2pd.exe','ProxyBridge_CLI.exe') {
    $p = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($name)) -ErrorAction SilentlyContinue
    if ($p) { Ok "$name running (PID $($p.Id -join ','))" }
    elseif ($name -eq 'ProxyBridge_CLI.exe') { Warn "$name not running (transparent Tor disabled)" }
    else { Warn "$name not running" }
}

Heading "Listening ports"
$tcpWanted = 9050, 9051, 4444, 4447, 5380
$anyTcp = $false
foreach ($port in $tcpWanted) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', $port)
        Ok "TCP :$port listening"
        $anyTcp = $true
    } catch {
        Warn "TCP :$port not listening"
    } finally {
        $client.Close()
    }
}
if (-not $anyTcp) { Warn "No expected TCP port is listening." }
foreach ($port in 5300,5380) {
    try {
        $u = Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue
        if ($u) { Ok "UDP :$port listening" } else { Warn "UDP :$port not listening" }
    } catch { }
}

Heading "System DNS"
try {
    Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
        Where-Object { $_.ServerAddresses -and $_.ServerAddresses.Count -gt 0 } |
        Select-Object InterfaceAlias, AddressFamily, @{n='Servers';e={$_.ServerAddresses -join ', '}} |
        Format-Table -AutoSize | Out-String | Write-Host
    $dns = Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
        Where-Object { $_.AddressFamily -eq 2 -and $_.ServerAddresses -contains '127.0.0.1' }
    if ($dns) { Ok "At least one IPv4 adapter uses 127.0.0.1" }
    else { Warn "No IPv4 adapter is pointing at 127.0.0.1 (system DNS may not be protected)" }
} catch {
    Warn "Could not read DNS settings: $($_.Exception.Message)"
}

Heading "WinINET proxy"
try {
    $p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
        -Name ProxyEnable, ProxyServer -ErrorAction SilentlyContinue
    Info "ProxyEnable = $($p.ProxyEnable)"
    Info "ProxyServer  = $($p.ProxyServer)"
    if ($p.ProxyEnable -eq 1 -and $p.ProxyServer) { Ok "Windows proxy is enabled" }
    else { Warn "Windows proxy is not enabled (fine for DNSCrypt-only mode)" }
} catch {
    Warn "Could not read WinINET proxy settings."
}

Heading "Windows Firewall kill switch"
# A system-wide ProxyBridge in transparent mode intentionally leaves the
# firewall in allow mode; the redirector itself is the kill switch.
$pbProcs = @(Get-CimInstance Win32_Process -Filter "Name='ProxyBridge_CLI.exe'" -ErrorAction SilentlyContinue)
$pbSystem = @($pbProcs | Where-Object { $_.CommandLine -match 'proxybridge-profile\.json' })
try {
    $profiles = Get-NetFirewallProfile -ErrorAction SilentlyContinue
    $profiles | Select-Object Name, DefaultOutboundAction | Format-Table -AutoSize | Out-String | Write-Host
    $blocked = @($profiles | Where-Object { [string]$_.DefaultOutboundAction -eq 'Block' })
    if ($blocked.Count -eq 3) { Ok "All profiles block outbound by default (proxy-mode kill switch)" }
    elseif ($pbSystem.Count -gt 0) { Ok "Transparent mode: firewall is in allow mode; ProxyBridge enforces TCP→Tor and UDP blocking" }
    elseif ($blocked.Count -gt 0) { Warn "Only $($blocked.Count)/3 profiles block outbound" }
    else { Bad "Default outbound is not Block and no system-wide ProxyBridge is running; kill switch is NOT active" }

    $rules = @(Get-NetFirewallRule -Group 'Entropy Shield' -ErrorAction SilentlyContinue)
    if ($rules.Count -gt 0) { Ok "$($rules.Count) Entropy Shield allow rule(s) present" }
    else { Warn "No Entropy Shield firewall rules found" }
} catch {
    Warn "Could not query Windows Firewall (run PowerShell as Administrator for full detail)."
}

Heading "Tor exit check (through SOCKS :9050)"
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
    $tor = & curl.exe -s --max-time 20 --socks5-hostname 127.0.0.1:9050 `
        https://check.torproject.org/api/ip 2>$null
    if ($LASTEXITCODE -eq 0 -and $tor) {
        Info $tor
        if ($tor -match '"IsTor"\s*:\s*true') { Ok "Traffic through SOCKS is a Tor exit" }
        else { Bad "SOCKS replied but the IP is not a Tor exit" }
    } else {
        Bad "Could not query check.torproject.org through Tor"
    }
} else {
    Warn "curl.exe not found; use the app's IP Check button instead."
}

Heading "Transparent routing / direct egress"
if ($curl -and $pbSystem.Count -gt 0) {
    Info "System-wide ProxyBridge is running: testing an app that ignores the proxy."
    $t = & curl.exe -sS --noproxy '*' --max-time 25 `
        https://check.torproject.org/api/ip 2>$null
    if ($LASTEXITCODE -eq 0 -and $t -match '"IsTor"\s*:\s*true') {
        Ok "No-proxy traffic is transparently routed through Tor"
    } elseif ($LASTEXITCODE -eq 0 -and $t) {
        Bad "No-proxy traffic left directly (IsTor is not true): $t"
    } else {
        Warn "No-proxy HTTPS failed; transparent routing may be down (run as Administrator for detail)"
    }
} elseif ($pbProcs.Count -gt 0) {
    Warn "ProxyBridge is running with a per-app profile ('Run any app through Tor'); skipping the global no-proxy test"
} elseif ($curl) {
    & curl.exe -sS --noproxy '*' --max-time 6 https://example.com -o NUL 2>$null
    if ($LASTEXITCODE -eq 0) {
        Bad "Direct HTTPS to example.com succeeded; kill switch may not be blocking"
    } else {
        Ok "Direct HTTPS failed/blocked (expected while PROTECTED in proxy mode)"
    }
}

Heading "DNSCrypt query through local resolver"
try {
    $r = Resolve-DnsName example.com -Server 127.0.0.1 -ErrorAction Stop |
        Where-Object { $_.IPAddress } | Select-Object -First 1
    if ($r) { Ok "127.0.0.1 resolved example.com -> $($r.IPAddress)" }
    else { Warn "127.0.0.1 returned no A record" }
} catch {
    Warn "Could not resolve through 127.0.0.1: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Transparent Tor (ProxyBridge) routes every app through Tor and blocks UDP." -ForegroundColor Cyan
Write-Host "In proxy mode, apps that ignore the proxy are blocked by the kill switch." -ForegroundColor Cyan
Write-Host "Use the app's browser/terminal profiles when transparent mode is unavailable." -ForegroundColor Cyan
