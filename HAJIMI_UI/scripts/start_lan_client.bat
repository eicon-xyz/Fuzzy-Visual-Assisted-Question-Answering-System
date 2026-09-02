@echo off
setlocal EnableExtensions

cd /d %~dp0..

echo [HAJIMI] LAN client setup ¡ª remote 8010 + L5 (hotspot / intranet)
python scripts\setup_lan_client.py
if errorlevel 1 (
    echo [HAJIMI] Setup failed. UI not started.
    endlocal
    exit /b 1
)

set "HAJIMI_LAN_BASE="
if exist "%TEMP%\hajimi_lan_base.txt" (
    set /p HAJIMI_LAN_BASE=<"%TEMP%\hajimi_lan_base.txt"
)
if defined HAJIMI_LAN_BASE (
    set L5_API_URL=%HAJIMI_LAN_BASE%
)

set HAJIMI_AUTO_LAUNCH_A_END=0
set HAJIMI_AUTO_LAUNCH_L5=0

call scripts\start_client.bat
set ERR=%ERRORLEVEL%
endlocal
exit /b %ERR%
