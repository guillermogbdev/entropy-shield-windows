#requires -Version 5.1
<#
.SYNOPSIS
    Install the extracted portable package into Program Files.

.DESCRIPTION
    This script lives in <package>\scripts.  It copies the package to
    %ProgramFiles%\Entropy Shield, applies a standard Program Files ACL,
    creates a Start Menu shortcut and registers the logon helper task.
    No Python, no network access and no setup-windows.ps1 are required.

.PARAMETER Target
    Installation directory. Defaults to %ProgramFiles%\Entropy Shield.

.PARAMETER NoShortcut
    Skip the Start Menu shortcut (useful for testing).

.PARAMETER NoHelperTask
    Skip the logon helper task (useful for testing).

.PARAMETER NoStopProcesses
    Do not stop a running Entropy Shield instance (useful for testing a
    throw-away target without touching the installed app).
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $env:ProgramFiles 'Entropy Shield'),
    [switch]$NoShortcut,
    [switch]$NoHelperTask,
    [switch]$NoStopProcesses
)

$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$srcExe = Join-Path $source 'Entropy Shield.exe'
if (-not (Test-Path $srcExe)) {
    throw "Portable package not found: $srcExe"
}

$targetFull = [IO.Path]::GetFullPath($Target).TrimEnd('\')
$sourceFull = [IO.Path]::GetFullPath($source).TrimEnd('\')
if ($sourceFull -ieq $targetFull) {
    throw "Source and target are the same folder: $source"
}

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting Administrator permission..." -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                 "`"$PSCommandPath`"", '-Target', "`"$Target`"")
    if ($NoShortcut) { $argList += '-NoShortcut' }
    if ($NoHelperTask) { $argList += '-NoHelperTask' }
    if ($NoStopProcesses) { $argList += '-NoStopProcesses' }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

Write-Host "Installing to $Target ..." -ForegroundColor Cyan
if (-not $NoStopProcesses) {
    Get-Process -Name 'Entropy Shield' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item (Join-Path $source '*') $Target -Recurse -Force

# Set the directory ACL explicitly, then let every copied child inherit it.
# (icacls /inheritance:r + /grant:r /T left files with an empty DACL.)
& takeown /F $Target /A /R /D Y | Out-Null
& icacls $Target /inheritance:r /grant:r `
    '*S-1-5-32-544:(OI)(CI)F' `
    '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
Get-ChildItem -LiteralPath $Target -Recurse -Force | ForEach-Object {
    & icacls $_.FullName /reset | Out-Null
}

if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $startMenu = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Entropy Shield.lnk'
    $lnk = $shell.CreateShortcut($startMenu)
    $lnk.TargetPath = Join-Path $Target 'Entropy Shield.exe'
    $lnk.WorkingDirectory = $Target
    $lnk.Description = 'Entropy Shield - Tor, DNSCrypt, I2P privacy stack'
    $lnk.Save()
    Write-Host "Start Menu shortcut: $startMenu"
}

if (-not $NoHelperTask) {
    try {
        & (Join-Path $PSScriptRoot 'install-helper-task.ps1') `
            -Exe (Join-Path $Target 'Entropy Shield.exe')
    } catch {
        Write-Warning "Could not register the logon helper task: $_"
        Write-Warning "The app still works; Connect will ask for UAC when needed."
    }
}

Write-Host ""
Write-Host "Installed: $(Join-Path $Target 'Entropy Shield.exe')" -ForegroundColor Green
Write-Host "You can now launch it from the Start Menu."
