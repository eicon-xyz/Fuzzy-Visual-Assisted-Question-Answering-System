@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\start_lan_client.bat
set ERR=%ERRORLEVEL%
if %ERR% GEQ 1 (
    echo.
    echo [HAJIMI] LAN client startup failed - see messages above.
    pause
)
endlocal
exit /b %ERR%
