#requires -Version 5.1
<#
.SYNOPSIS
    Install the Python dependency and download the privacy binaries for the
    Windows build of Entropy Shield.

.DESCRIPTION
    Downloads the official Tor Expert Bundle, dnscrypt-proxy and i2pd releases
    into .\bin and installs PyQt6.  Run it from an ordinary PowerShell window;
    no Administrator rights are needed for setup itself.  The ProxyBridge
    installer may request elevation to register its Windows service.

    The binaries are fetched over HTTPS from their official release locations.
    For maximum assurance, verify the signatures/hashes published by each
    project before use.

.PARAMETER SkipDownload
    Only install/check PyQt6 and create the bin folder.

.PARAMETER Force
    Re-download even when a binary already exists.
#>
[CmdletBinding()]
param(
    [switch]$SkipDownload,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
$bin  = Join-Path $root 'bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Get-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python 3.10+ was not found in PATH. Install it from https://python.org first."
}

function Download([string]$Url, [string]$Destination) {
    Write-Host "    $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 300
}

function Get-GitHubAsset([string]$Repo, [string]$Pattern) {
    $headers = @{ 'User-Agent' = 'entropy-shield-windows-setup' }
    $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 60
    $asset = $release.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1
    if (-not $asset) { throw "No release asset matching '$Pattern' in $Repo." }
    return @{ url = $asset.browser_download_url; name = $asset.name }
}

function Get-GitHubAssetAny([string]$Repo, [string]$Pattern) {
    # ProxyBridge publishes Windows and macOS builds as separate releases, so
    # /releases/latest can point at the macOS one.  Scan the recent releases and
    # take the first matching asset.
    $headers = @{ 'User-Agent' = 'entropy-shield-windows-setup' }
    $releases = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases?per_page=30" -TimeoutSec 60
    foreach ($release in $releases) {
        $asset = $release.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1
        if ($asset) { return @{ url = $asset.browser_download_url; name = $asset.name } }
    }
    throw "No release asset matching '$Pattern' in $Repo."
}

Write-Step "Checking Python"
$python = Get-Python
& $python --version
if ($LASTEXITCODE -ne 0) { throw "Python did not run correctly." }

Write-Step "Installing PyQt6"
& $python -m pip install --disable-pip-version-check --upgrade PyQt6
if ($LASTEXITCODE -ne 0) { throw "pip install PyQt6 failed." }

if ($SkipDownload) {
    Write-Step "Skipping binary downloads"
    exit 0
}

# ── Tor Expert Bundle ───────────────────────────────────────────────────────
$torExe = Join-Path $bin 'tor\tor\tor.exe'
if ($Force -or -not (Test-Path $torExe)) {
    Write-Step "Downloading Tor Expert Bundle"
    try {
        $dl = Invoke-RestMethod -Uri 'https://aus1.torproject.org/torbrowser/update_3/release/downloads.json' -TimeoutSec 60
        $browserUrl = $dl.downloads.win64.ALL.binary
        $version = '16.0'
        if ($browserUrl -match '/([0-9]+\.[0-9]+(?:\.[0-9]+)?)/') { $version = $Matches[1] }
        $torUrl = "https://dist.torproject.org/torbrowser/$version/tor-expert-bundle-windows-x86_64-$version.tar.gz"
        $tar = Join-Path $env:TEMP "tor-expert-$version.tar.gz"
        Download $torUrl $tar
        $dest = Join-Path $bin 'tor'
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        tar -xzf $tar -C $dest
        Remove-Item $tar -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Could not download the Tor Expert Bundle: $_"
        Write-Warning "Install Tor Browser instead; the app also finds its tor.exe automatically."
    }
} else {
    Write-Host "    Tor already present: $torExe"
}

# ── dnscrypt-proxy ──────────────────────────────────────────────────────────
$dnsExe = Join-Path $bin 'dnscrypt-proxy\dnscrypt-proxy.exe'
if ($Force -or -not (Test-Path $dnsExe)) {
    Write-Step "Downloading dnscrypt-proxy"
    $asset = Get-GitHubAsset 'DNSCrypt/dnscrypt-proxy' '^dnscrypt-proxy-win64-.*\.zip$'
    $zip = Join-Path $env:TEMP $asset.name
    Download $asset.url $zip
    $tmp = Join-Path $env:TEMP ("dnscrypt-" + [guid]::NewGuid().ToString('N'))
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $found = Get-ChildItem -Path $tmp -Recurse -Filter 'dnscrypt-proxy.exe' | Select-Object -First 1
    if (-not $found) { throw "dnscrypt-proxy.exe was not found in the downloaded archive." }
    $dest = Join-Path $bin 'dnscrypt-proxy'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $found.DirectoryName '*') $dest -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "    dnscrypt-proxy already present: $dnsExe"
}

# ── i2pd ────────────────────────────────────────────────────────────────────
$i2pExe = Join-Path $bin 'i2pd\i2pd.exe'
if ($Force -or -not (Test-Path $i2pExe)) {
    Write-Step "Downloading i2pd"
    $asset = Get-GitHubAsset 'PurpleI2P/i2pd' '^i2pd_.*win64.*\.zip$'
    $zip = Join-Path $env:TEMP $asset.name
    Download $asset.url $zip
    $dest = Join-Path $bin 'i2pd'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "    i2pd already present: $i2pExe"
}

# ── ProxyBridge (transparent Tor) ───────────────────────────────────────────
$pbDest = Join-Path $env:LOCALAPPDATA 'entropy-shield\proxybridge'
$pbCli  = Join-Path $pbDest 'ProxyBridge_CLI.exe'
if ($Force -or -not (Test-Path $pbCli)) {
    Write-Step "Downloading ProxyBridge (transparent Tor)"
    try {
        $asset = Get-GitHubAssetAny 'InterceptSuite/ProxyBridge' '^ProxyBridge-Setup-.*\.exe$'
        $setup = Join-Path $env:TEMP $asset.name
        Download $asset.url $setup
        New-Item -ItemType Directory -Force -Path $pbDest | Out-Null
        # NSIS: /D=<dir> must be the last argument and must not be quoted.
        $installer = Start-Process -FilePath $setup -ArgumentList '/S', "/D=$pbDest" -Wait -PassThru
        Remove-Item $setup -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $pbCli)) {
            throw "ProxyBridge installer exited $($installer.ExitCode) but $pbCli was not created."
        }
        Write-Host "    Installed: $pbCli"
    } catch {
        Write-Warning "Could not install ProxyBridge: $_"
        Write-Warning "Transparent Tor will be unavailable; apps must use the SOCKS proxy."
    }
} else {
    Write-Host "    ProxyBridge already present: $pbCli"
}

Write-Step "Done"
Write-Host "Tor:             $(if (Test-Path $torExe) { $torExe } else { 'not found (install Tor Browser)' })"
Write-Host "dnscrypt-proxy:  $(if (Test-Path $dnsExe) { $dnsExe } else { 'not found' })"
Write-Host "i2pd:            $(if (Test-Path $i2pExe) { $i2pExe } else { 'not found' })"
Write-Host "ProxyBridge:     $(if (Test-Path $pbCli) { $pbCli } else { 'not found (transparent Tor unavailable)' })"
Write-Host ""
Write-Host "Start the app with:  .\run-windows.bat" -ForegroundColor Green
