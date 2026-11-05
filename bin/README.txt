Put the Windows privacy binaries here, or run ..\scripts\setup-windows.ps1
to download them automatically.

Expected layout after setup:

  bin\tor\tor\tor.exe                     Tor Expert Bundle
  bin\tor\tor\pluggable_transports\...    obfs4proxy / lyrebird (optional bridges)
  bin\dnscrypt-proxy\dnscrypt-proxy.exe
  bin\i2pd\i2pd.exe

The app also searches:

  * the usual Tor Browser / dnscrypt-proxy / i2pd installation folders
  * PATH
  * the "binaries" section of %APPDATA%\entropy-shield\config.json
  * these environment variables:
        ENTROPY_SHIELD_TOR
        ENTROPY_SHIELD_DNSCRYPT_PROXY
        ENTROPY_SHIELD_I2PD

Official sources:
  Tor Expert Bundle:  https://dist.torproject.org/torbrowser/
  dnscrypt-proxy:     https://github.com/DNSCrypt/dnscrypt-proxy/releases
  i2pd:               https://github.com/PurpleI2P/i2pd/releases
