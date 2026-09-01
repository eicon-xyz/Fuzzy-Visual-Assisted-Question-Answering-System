@echo off
setlocal EnableExtensions

REM ============================================================
REM  HAJIMI launcher - local_vision mode (no OmniParser :9800)
REM  IMPORTANT: keep this file ASCII-only (GBK codepage safe).
REM  Run from a Windows-local path like C:\HAJIMI, NOT from
REM  \\wsl.localhost\... (CMD cannot cd to UNC paths).
REM ============================================================

cd /d "%~dp0HAJIMI_UI" 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot enter HAJIMI_UI at "%~dp0HAJIMI_UI"
    echo         UNC paths (\\wsl.localhost\...) are not supported by CMD.
    echo         Please copy the repo to C:\HAJIMI and run from there.
    pause
    exit /b 1
)

REM local_vision: L4 vision planning (DeepSeek) + L5 UIA execution.
REM Old GPU tunnel path kept in scripts\start_local_one_click.bat
call scripts\start_local_vision.bat
set ERR=%ERRORLEVEL%

if %ERR% GEQ 1 (
    echo.
    if %ERR% EQU 2 (
        echo [HAJIMI] Startup completed with warnings - UI may be open; status bar retries every 10s.
    ) else (
        echo [HAJIMI] Startup failed - see messages above.
    )
    pause
) else (
    echo.
    echo [INFO] Launcher done. Check HAJIMI-* console windows. Close this window if UI is up.
    timeout /t 5 /nobreak >nul
)
endlocal
exit /b %ERR%
