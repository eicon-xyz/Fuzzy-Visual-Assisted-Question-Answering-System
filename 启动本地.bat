@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
REM 无 :9800 纯视觉模式：L4 视觉(DeepSeek) + L5 UIA 绑定执行
REM （原 GPU 隧道路径保留在 scripts\start_local_one_click.bat / start_gpu_one_click.bat）
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
