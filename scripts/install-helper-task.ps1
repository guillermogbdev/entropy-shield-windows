#requires -Version 5.1
<#
.SYNOPSIS
    Install the persistent, elevated Entropy Shield helper as a logon task.

.DESCRIPTION
    Linux runs the privileged backend as a systemd service.  Windows normally
    starts the helper with UAC every time the app connects.  This script
    registers a per-user scheduled task that starts the same helper elevated at
    logon (no UAC) and keeps it alive while the user is logged in.

    The helper still listens only on 127.0.0.1, requires the random token from
    %LOCALAPPDATA%\entropy-shield\daemon.json, and performs the same operations
    as the UAC-started helper.  Remove it at any time with
    scripts\uninstall-windows.ps1 or:
      Unregister-ScheduledTask -TaskName 'Entropy Shield Helper' -Confirm:$false

.PARAMETER Exe
    Path to Entropy Shield.exe.  Defaults to the Program Files install, then
    the portable dist\ build.
#>
[CmdletBinding()]
param([string]$Exe = "")

$ErrorActionPreference = 'Stop'
$taskName = 'Entropy Shield Helper'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting Administrator permission..." -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Exe) { $argList += @('-Exe', "`"$Exe`"") }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

if (-not $Exe) {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Entropy Shield\Entropy Shield.exe'),
        (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\Entropy Shield\Entropy Shield.exe')
    )
    $Exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Exe -or -not (Test-Path $Exe)) {
    throw "Entropy Shield.exe was not found. Pass -Exe <path> or install the app first."
}
$Exe = (Resolve-Path $Exe).Path
$workDir = Split-Path -Parent $Exe
$user = "$env:USERDOMAIN\$env:USERNAME"

Write-Host "Registering logon helper task..." -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute $Exe -Argument '--windows-helper-persist' -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $taskPrincipal -Settings $settings -Force `
    -Description 'Persistent elevated helper for Entropy Shield (loopback only).' | Out-Null
# A previous helper may still be registered as running while its process was
# just killed by the installer; with MultipleInstances=IgnoreNew the start
# would be ignored and the task would stay Ready.  Stop and restart it cleanly.
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
$info = Get-ScheduledTask -TaskName $taskName
Write-Host "Task: $taskName ($($info.State))" -ForegroundColor Green
Write-Host "Helper: $Exe --windows-helper-persist"
Write-Host "The app will now reuse it and skip the UAC prompt while it is running."
