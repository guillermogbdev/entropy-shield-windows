#requires -Version 5.1
<#
.SYNOPSIS
    Remove the installed app and restore network settings.

.DESCRIPTION
    Stops the GUI/helper, runs the application's own recovery path
    (--windows-restore) to restore the firewall, DNS and proxy, then removes
    the Program Files installation and the Start Menu shortcut.

    Recovery runs inside Entropy Shield.exe, so Python is not required.

.PARAMETER Target
    Installation directory.  Defaults to %ProgramFiles%\Entropy Shield.

.PARAMETER RemoveData
    Also delete %APPDATA%\entropy-shield and %LOCALAPPDATA%\entropy-shield
    (settings, Tor cache, DNSCrypt/i2pd data and the onion service keys).
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $env:ProgramFiles 'Entropy Shield'),
    [switch]$RemoveData
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $extra = @()
    if ($RemoveData) { $extra += '-RemoveData' }
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                 '-Target', "`"$Target`"") + $extra
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

# Stop the GUI first so it cannot reconnect or re-apply the kill switch while
# the uninstaller is cleaning up.  In the frozen build the elevated helper is
# the same EXE, so it is stopped here too; in a source checkout it stays alive
# until Invoke-EntropyShieldRestore sends it a shutdown command.
Write-Host "Stopping Entropy Shield..." -ForegroundColor Cyan
Get-Process -Name 'Entropy Shield' -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Remove the persistent logon helper before deleting the installation so it
# cannot be restarted at the next logon.
Unregister-ScheduledTask -TaskName 'Entropy Shield Helper' `
    -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

function Invoke-EntropyShieldRestore {
    $candidates = @(
        (Join-Path $Target 'Entropy Shield.exe'),
        (Join-Path $root 'dist\Entropy Shield\Entropy Shield.exe')
    )
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            Write-Host "Restoring network settings through: $exe"
            $proc = Start-Process -FilePath $exe -ArgumentList '--windows-restore' `
                                  -Wait -PassThru -WindowStyle Hidden
            return [int]$proc.ExitCode
        }
    }

    Write-Host "No Entropy Shield.exe found; using Python from $root."
    $tmp = Join-Path $env:TEMP ("entropy-shield-uninstall-" + [guid]::NewGuid().ToString('N') + ".py")
    $code = @'
import os, sys
sys.path.insert(0, os.environ["ENTROPY_SHIELD_ROOT"])
from core.windows.restore import main
raise SystemExit(main())
'@
    Set-Content -Path $tmp -Value $code -Encoding UTF8
    $env:ENTROPY_SHIELD_ROOT = $root
    $env:PYTHONPATH = $root
    try {
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python $tmp
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 $tmp
        } else {
            throw "No Entropy Shield.exe and no Python were found."
        }
        return [int]$LASTEXITCODE
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        Remove-Item Env:ENTROPY_SHIELD_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
}

Write-Host "Restoring Windows Firewall, DNS and proxy settings..." -ForegroundColor Cyan
$rc = Invoke-EntropyShieldRestore
if ($rc -ne 0) {
    Write-Warning "Recovery reported an error (exit $rc). See $env:LOCALAPPDATA\entropy-shield\restore.log. Continuing with file removal; run scripts\restore-windows.ps1 afterwards if the network is still blocked."
}

$startMenu = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Entropy Shield.lnk'
Remove-Item $startMenu -Force -ErrorAction SilentlyContinue
if (Test-Path $Target) {
    Write-Host "Removing $Target ..."
    Remove-Item $Target -Recurse -Force
}

# The app enables autostart through HKCU; remove that value if it is present.
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
    -Name 'EntropyShield' -ErrorAction SilentlyContinue

Remove-Item (Join-Path $env:LOCALAPPDATA 'entropy-shield\daemon.json') `
    -Force -ErrorAction SilentlyContinue

if ($RemoveData) {
    Write-Host "Removing user data..."
    Remove-Item (Join-Path $env:APPDATA 'entropy-shield') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:LOCALAPPDATA 'entropy-shield') -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Entropy Shield removed." -ForegroundColor Green
