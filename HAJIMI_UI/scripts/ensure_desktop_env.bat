@echo off
setlocal EnableExtensions
cd /d %~dp0..\..\desktop

echo ============================================================
echo  HAJIMI Desktop - install Electron B-end dependencies
echo ============================================================

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] node not found - install Node.js 20+ first
    pause
    exit /b 1
)

where pnpm >nul 2>&1
if errorlevel 1 (
    echo [INFO] pnpm not found - enabling via corepack ...
    corepack enable pnpm
)

where pnpm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pnpm unavailable - run: npm install -g pnpm
    pause
    exit /b 1
)

echo [1/2] pnpm install ...
call pnpm install
if errorlevel 1 goto fail

echo [2/2] build desktop app ...
call pnpm run build
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  Desktop app ready. Launch with: start_desktop.bat
echo ============================================================
endlocal
exit /b 0

:fail
echo [ERROR] desktop env setup failed
pause
endlocal
exit /b 1
