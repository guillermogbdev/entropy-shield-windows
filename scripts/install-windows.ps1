#requires -Version 5.1
<#
.SYNOPSIS
    Install the built Windows app into Program Files.

.DESCRIPTION
    Run scripts\build-windows.ps1 first.  Installing under Program Files makes
    the elevated helper execute code that ordinary users cannot modify, which
    is the Windows equivalent of the Linux package's root-owned /opt tree.

.PARAMETER Target
    Installation directory.  Defaults to %ProgramFiles%\Entropy Shield.
#>
[CmdletBinding()]
param([string]$Target = (Join-Path $env:ProgramFiles 'Entropy Shield'))

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'dist\Entropy Shield'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting Administrator permission..." -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Target', "`"$Target`"")
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

if (-not (Test-Path (Join-Path $source 'Entropy Shield.exe'))) {
    throw "Build not found at $source. Run scripts\build-windows.ps1 first."
}

Write-Host "Installing to $Target ..." -ForegroundColor Cyan
Get-Process -Name 'Entropy Shield' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item (Join-Path $source '*') $Target -Recurse -Force

# The application only needs to read its installation directory; user data
# lives in %APPDATA% / %LOCALAPPDATA%.
& icacls $Target /inheritance:r /grant:r `
    '*S-1-5-32-544:(OI)(CI)F' `
    '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-32-545:(OI)(CI)RX' /T | Out-Null

$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Entropy Shield.lnk'
$lnk = $shell.CreateShortcut($startMenu)
$lnk.TargetPath = Join-Path $Target 'Entropy Shield.exe'
$lnk.WorkingDirectory = $Target
$lnk.Description = 'Entropy Shield — Tor, DNSCrypt, I2P privacy stack'
$lnk.Save()

# Optional but recommended: a persistent elevated helper at logon removes the
# UAC prompt on every Connect (the closest Windows equivalent to systemd).
try {
    & (Join-Path $PSScriptRoot 'install-helper-task.ps1') `
        -Exe (Join-Path $Target 'Entropy Shield.exe')
} catch {
    Write-Warning "Could not register the logon helper task: $_"
    Write-Warning "The app still works; Connect will ask for UAC when needed."
}

Write-Host ""
Write-Host "Installed: $(Join-Path $Target 'Entropy Shield.exe')" -ForegroundColor Green
Write-Host "Start Menu shortcut: $startMenu"
Write-Host "The logon helper task avoids the UAC prompt on Connect."
