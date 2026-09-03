@echo off
setlocal EnableExtensions
cd /d %~dp0..\..\desktop

if not exist "out\main\main.mjs" (
    echo [INFO] desktop not built yet - running build ...
    call pnpm run build
    if errorlevel 1 goto fail
)

if not exist "node_modules\.bin\electron.cmd" (
    echo [ERROR] electron not installed - run ensure_desktop_env.bat first
    pause
    exit /b 1
)

echo [HAJIMI] Starting HAJIMI Desktop - L5 Sidecar auto-launch handled by the app on port 8011 ...
start "" "node_modules\.bin\electron.cmd" .
endlocal
exit /b 0

:fail
echo [ERROR] desktop build failed - check Node.js and run ensure_desktop_env.bat
pause
endlocal
exit /b 1
