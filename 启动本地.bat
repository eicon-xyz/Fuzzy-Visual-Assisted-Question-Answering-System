@echo off
setlocal EnableExtensions

REM ============================================================
REM  HAJIMI launcher - local_vision mode (no OmniParser :9800)
REM  ASCII-only. Logs everything to local_vision_run.log
REM ============================================================

set "LOG=%~dp0HAJIMI_UI\scripts\local_vision_run.log"
echo === HAJIMI launcher %date% %time% ===>>"%LOG%"

cd /d "%~dp0HAJIMI_UI" >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot enter HAJIMI_UI at "%~dp0HAJIMI_UI">>"%LOG%"
    echo [ERROR] Cannot enter HAJIMI_UI at "%~dp0HAJIMI_UI"
    echo [ERROR] UNC paths are not supported. Copy repo to C:\HAJIMI.
    pause
    exit /b 1
)

echo [STEP] calling scripts\start_local_vision.bat ...>>"%LOG%"
call scripts\start_local_vision.bat >>"%LOG%" 2>&1
set ERR=%ERRORLEVEL%
echo [STEP] start_local_vision.bat returned %ERR%>>"%LOG%"

if %ERR% GEQ 1 (
    echo.
    echo [HAJIMI] Startup failed - see messages above. Log: %LOG%
    type "%LOG%"
    pause
) else (
    echo.
    echo [INFO] Launcher done. Check HAJIMI-* console windows. Log: %LOG%
    ping -n 6 127.0.0.1 >nul 2>&1
)
echo === END %date% %time% ===>>"%LOG%"
endlocal
exit /b %ERR%
