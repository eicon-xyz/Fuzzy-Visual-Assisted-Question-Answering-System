@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\start_local_one_click.bat
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
