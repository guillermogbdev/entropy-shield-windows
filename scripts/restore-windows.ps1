#requires -Version 5.1
<#
.SYNOPSIS
    Restore Windows Firewall, DNS and proxy settings after a crash.

.DESCRIPTION
    Entropy Shield normally restores these when you click Disconnect or Panic.
    If the GUI or helper was killed, run this script as Administrator once.
    It removes only the rules and values Entropy Shield created.

    The restore runs inside the application itself (the installed or built
    Entropy Shield.exe, with --windows-restore), so it also works on machines
    where Python is not installed.  A source-tree fallback uses Python when no
    EXE is available.

.PARAMETER Target
    Installation directory.  Defaults to %ProgramFiles%\Entropy Shield.
#>
[CmdletBinding()]
param([string]$Target = (Join-Path $env:ProgramFiles 'Entropy Shield'))

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting Administrator permission..." -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                 '-Target', "`"$Target`"")
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

function Invoke-EntropyShieldRestore {
    $candidates = @(
        (Join-Path $Target 'Entropy Shield.exe'),
        (Join-Path $root 'Entropy Shield.exe'),
        (Join-Path $root 'dist\Entropy Shield\Entropy Shield.exe')
    )
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            Write-Host "Restoring through: $exe"
            $proc = Start-Process -FilePath $exe -ArgumentList '--windows-restore' `
                                  -Wait -PassThru -WindowStyle Hidden
            return [int]$proc.ExitCode
        }
    }

    # Source-tree fallback for developers who have not built the EXE yet.
    Write-Host "No Entropy Shield.exe found; using Python from $root."
    $tmp = Join-Path $env:TEMP ("entropy-shield-restore-" + [guid]::NewGuid().ToString('N') + ".py")
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

$rc = Invoke-EntropyShieldRestore
if ($rc -ne 0) {
    throw "The restore failed (exit $rc). See $env:LOCALAPPDATA\entropy-shield\restore.log."
}
Write-Host "Done. You can reconnect or close this window." -ForegroundColor Green
