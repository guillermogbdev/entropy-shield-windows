@echo off
rem Emergency recovery: restore the firewall, DNS and proxy after an
rem unexpected shutdown, without opening the GUI.  Accept the UAC prompt.
set "EXE=%~dp0..\Entropy Shield.exe"
if not exist "%EXE%" set "EXE=%ProgramFiles%\Entropy Shield\Entropy Shield.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%EXE%' -ArgumentList '--windows-restore' -Verb RunAs"
