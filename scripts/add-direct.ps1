#requires -Version 5.1
<#
.SYNOPSIS
    Mark a process or endpoint as direct (bypass Tor) in Entropy Shield.

.DESCRIPTION
    Transparent mode sends every TCP connection through Tor.  Endpoints that are
    only reachable directly (campus/corporate LLM APIs, VPN servers, internal
    services) show up in proxybridge.log as "proxy replied 0x05".  This script
    edits the per-user config so those destinations stay direct:

      -Process <name.exe>   adds a Per-App Routing rule with action "direct"
      -Address <IP/CIDR>    adds the endpoint to vpn.allow
      -ListRefused          lists endpoints Tor refused in the current log

    The helper reloads the config on the next Connect; no restart is needed.
    The GUI exposes the same settings under Settings -> Routing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\add-direct.ps1 -Process opencode-cli.exe

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\add-direct.ps1 -Address 129.241.121.18/32

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\add-direct.ps1 -ListRefused
#>
[CmdletBinding()]
param(
    [string]$Process = "",
    [string]$Address = "",
    [switch]$ListRefused
)

$ErrorActionPreference = 'Stop'
$cfgPath = Join-Path $env:APPDATA 'entropy-shield\config.json'
$logPath = Join-Path $env:LOCALAPPDATA 'entropy-shield\proxybridge.log'

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  add-direct.ps1 -Process <name.exe>"
    Write-Host "  add-direct.ps1 -Address <IP or CIDR>"
    Write-Host "  add-direct.ps1 -ListRefused"
}

function Test-Endpoint([string]$value) {
    $parts = $value -split '/', 2
    $ip = $null
    if (-not [System.Net.IPAddress]::TryParse($parts[0], [ref]$ip)) {
        return $false
    }
    if ($parts.Count -eq 2) {
        $prefix = 0
        if (-not [int]::TryParse($parts[1], [ref]$prefix)) { return $false }
        $max = if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) { 32 } else { 128 }
        if ($prefix -lt 0 -or $prefix -gt $max) { return $false }
    }
    return $true
}

if ($ListRefused) {
    if (-not (Test-Path $logPath)) {
        Write-Host "No proxybridge.log yet. Connect once with transparent Tor, then retry."
        exit 0
    }
    $text = Get-Content $logPath -Raw
    $destinations = [regex]::Matches(
        $text, 'CONNECT to ([0-9A-Fa-f:.]+:\d+) failed - proxy replied 0x05') |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
    if (-not $destinations) {
        Write-Host "No refused endpoints found in the current log."
        exit 0
    }
    Write-Host "Endpoints Tor refused (likely need a direct route):"
    foreach ($dest in $destinations) {
        $ip = $dest -replace ':\d+$', ''
        $cidr = if ($ip -match ':') { "$ip/128" } else { "$ip/32" }
        Write-Host ("  {0}" -f $dest)
        Write-Host ("    -> powershell -ExecutionPolicy Bypass -File .\scripts\add-direct.ps1 -Address {0}" -f $cidr)
    }
    exit 0
}

if (-not $Process -and -not $Address) {
    Show-Usage
    exit 1
}

if (-not (Test-Path $cfgPath)) {
    Write-Host "Config not found at $cfgPath. Run Entropy Shield once first." -ForegroundColor Red
    exit 1
}

$backup = "$cfgPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $cfgPath $backup -Force
$json = Get-Content $cfgPath -Raw | ConvertFrom-Json

if ($Process) {
    if ($Process -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,31}$') {
        Write-Host "Invalid process name: $Process" -ForegroundColor Red
        exit 1
    }
    if (-not $json.per_app_routing) {
        $json | Add-Member -NotePropertyName per_app_routing `
            -NotePropertyValue ([pscustomobject]@{ enabled = $true; rules = @() })
    }
    $rules = @($json.per_app_routing.rules) |
        Where-Object { $_.uid_or_user -ne $Process }
    $rules += [pscustomobject]@{
        name        = "$Process direct"
        uid_or_user = $Process
        action      = "direct"
    }
    $json.per_app_routing.rules = @($rules)
    $json.per_app_routing.enabled = $true
    Write-Host "Per-App Routing: $Process -> Direct" -ForegroundColor Green
}

if ($Address) {
    if (-not (Test-Endpoint $Address)) {
        Write-Host "Invalid address or CIDR: $Address" -ForegroundColor Red
        exit 1
    }
    if (-not $json.vpn) {
        $json | Add-Member -NotePropertyName vpn `
            -NotePropertyValue ([pscustomobject]@{ auto_detect = $true; allow = @() })
    }
    $allow = @($json.vpn.allow)
    if ($allow -notcontains $Address) { $allow += $Address }
    $json.vpn.allow = @($allow)
    Write-Host "Direct endpoint: $Address (vpn.allow)" -ForegroundColor Green
}

$out = $json | ConvertTo-Json -Depth 20
[IO.File]::WriteAllText($cfgPath, $out, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Saved:  $cfgPath"
Write-Host "Backup: $backup"
Write-Host "Reconnect in Entropy Shield (Disconnect -> Connect) to apply the change."
