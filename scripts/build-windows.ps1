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
        python -m pip install --disable-pip-version-check --upgrade pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed." }
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
        'main.py'
    )
    python -m PyInstaller @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    $dist = Join-Path $root 'dist\Entropy Shield'
    if (Test-Path (Join-Path $root 'bin')) {
        Copy-Item (Join-Path $root 'bin') $dist -Recurse -Force
    }
    Write-Host ""
    Write-Host "Built: $dist\Entropy Shield.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
