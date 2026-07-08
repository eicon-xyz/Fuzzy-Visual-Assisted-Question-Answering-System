@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\start_gpu_one_click.bat
set ERR=%ERRORLEVEL%
if %ERR% GEQ 1 (
    echo.
    if %ERR% EQU 2 (
        echo [HAJIMI] 启动完成但有警告 — UI 可能已打开，状态栏将显示未连接并每 10s 重试。
    ) else (
        echo [HAJIMI] 启动未完全成功 — 见上方日志。
    )
    pause
)
endlocal
exit /b %ERR%
