#requires -Version 5.1
<#
.SYNOPSIS
    Build a portable one-folder Windows executable with PyInstaller.

.DESCRIPTION
    The result is dist\Entropy Shield\Entropy Shield.exe.  The privacy
    binaries in .\bin are copied next to the EXE so the frozen build finds
    them.  Run setup-windows.ps1 first.
#>
[CmdletBinding()]
param([switch]$SkipInstall)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not $SkipInstall) {
        python -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements-build.txt')
        if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements-build.txt failed." }
    }

    $pyiArgs = @(
        '--noconfirm', '--clean', '--windowed',
        '--name', 'Entropy Shield',
        '--add-data', 'gui/icons;gui/icons',
        '--add-data', 'logos;logos',
        '--add-data', 'Fonts;Fonts',
        '--collect-submodules', 'core',
        '--collect-submodules', 'gui',
        '--hidden-import', 'core.windows.daemon_win',
        '--hidden-import', 'PyQt6.QtSvg',
        '--version-file', 'packaging/windows-version-info.txt',
        'main.py'
    )
    python -m PyInstaller @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    $dist = Join-Path $root 'dist\Entropy Shield'
    if (Test-Path (Join-Path $root 'bin')) {
        Copy-Item (Join-Path $root 'bin') $dist -Recurse -Force
    }

    # Bundle ProxyBridge/WinDivert so a fresh Windows machine gets transparent
    # mode without setup-windows.ps1, Python or an extra download.
    $pbSrc = Join-Path $env:LOCALAPPDATA 'entropy-shield\proxybridge'
    $pbDst = Join-Path $dist 'bin\proxybridge'
    if (Test-Path (Join-Path $pbSrc 'ProxyBridge_CLI.exe')) {
        New-Item -ItemType Directory -Force -Path $pbDst | Out-Null
        Copy-Item (Join-Path $pbSrc '*') $pbDst -Recurse -Force
        Copy-Item (Join-Path $root 'packaging\portable\PROXYBRIDGE-LICENSE.txt') $pbDst -Force
    } else {
        Write-Warning "ProxyBridge not found in $pbSrc; transparent mode will need scripts\setup-windows.ps1."
    }

    # Portable first-run files, helper scripts and documentation.
    $portable = Join-Path $root 'packaging\portable'
    if (Test-Path $portable) {
        Get-ChildItem $portable -File |
            Where-Object { $_.Name -ne 'PROXYBRIDGE-LICENSE.txt' } |
            Copy-Item -Destination $dist -Force
    }
    $scriptsDst = Join-Path $dist 'scripts'
    New-Item -ItemType Directory -Force -Path $scriptsDst | Out-Null
    foreach ($name in 'install-portable.ps1', 'install-helper-task.ps1',
                      'check-windows.ps1', 'restore-windows.ps1',
                      'add-direct.ps1') {
        Copy-Item (Join-Path $root "scripts\$name") $scriptsDst -Force
    }
    Copy-Item (Join-Path $root 'LICENSE') $dist -Force
    Copy-Item (Join-Path $root 'README.md') $dist -Force
    Copy-Item (Join-Path $root 'SECURITY.md') $dist -Force

    Write-Host ""
    Write-Host "Built: $dist\Entropy Shield.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
