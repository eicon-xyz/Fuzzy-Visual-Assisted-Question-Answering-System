@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0..

set VENV_PY=server\.venv\Scripts\python.exe

if /I "%HAJIMI_RECREATE_VENV%"=="1" (
    echo [HAJIMI-L5] Force recreate requested.
    if exist server\.venv (
        echo [HAJIMI-L5] Removing server\.venv ...
        rmdir /s /q server\.venv 2>nul
    )
)

if not exist "%VENV_PY%" (
    echo [HAJIMI-L5] Creating server virtual environment...
    python -m venv server\.venv
    if errorlevel 1 (
        echo [HAJIMI-L5] ERROR: failed to create server\.venv
        exit /b 1
    )
) else (
    echo [HAJIMI-L5] server\.venv exists — refresh dependencies.
)

:install_deps
echo [HAJIMI-L5] Installing server dependencies into server\.venv ...
set "_HAJIMI_PROXY_ENABLE="
for /f "tokens=3" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2^>nul ^| findstr ProxyEnable') do set "_HAJIMI_PROXY_ENABLE=%%A"
if /I "%_HAJIMI_PROXY_ENABLE%"=="0x1" (
    echo [HAJIMI-L5] Disabling IE proxy for pip install ^(will restore after^) ...
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
)
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r server\requirements.txt
set "_PIP_ERR=%ERRORLEVEL%"
if /I "%_HAJIMI_PROXY_ENABLE%"=="0x1" (
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul
)
if not "%_PIP_ERR%"=="0" (
    echo [HAJIMI-L5] ERROR: pip install failed
    exit /b 1
)

echo [HAJIMI-L5] L5 web automation uses your installed Edge/Chrome via Playwright.
echo [HAJIMI-L5] If browser tools fail, install/update Edge or Chrome, or run:
echo [HAJIMI-L5]   "%VENV_PY%" -m playwright install chromium

echo [HAJIMI-L5] Verifying installation...
"%VENV_PY%" -c "import fastapi, uvicorn, pydantic, sqlalchemy, psutil; print('fastapi', fastapi.__version__, 'sqlalchemy', sqlalchemy.__version__, 'psutil', psutil.__version__)"
if errorlevel 1 (
    echo [HAJIMI-L5] ERROR: venv verification failed
    exit /b 1
)

echo.
echo [HAJIMI-L5] Done. Start L5 Sidecar with: scripts\start_server.bat
endlocal
