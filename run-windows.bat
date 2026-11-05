@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python main.py %*
) else (
    py -3 main.py %*
)
endlocal
