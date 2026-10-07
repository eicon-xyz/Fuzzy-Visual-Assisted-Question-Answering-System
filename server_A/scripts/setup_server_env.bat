@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0..

set VENV_PY=server\.venv\Scripts\python.exe
set FASTAPI_SITE=server\.venv\Lib\site-packages\fastapi
set _HAJIMI_VERIFY_RETRIED=0

if not defined HAJIMI_L5_PORT set HAJIMI_L5_PORT=8011

:begin
if /I "%HAJIMI_RECREATE_VENV%"=="1" (
    echo [HAJIMI-L5] Force recreate requested.
    set HAJIMI_PORT=%HAJIMI_L5_PORT%
    call "%~dp0stop_server_hint.bat"
    if exist server\.venv (
        echo [HAJIMI-L5] Removing server\.venv ...
        rmdir /s /q server\.venv 2>nul
        if exist server\.venv (
            echo [HAJIMI-L5] ERROR: Cannot remove server\.venv ¡ª stop L5 server first:
            echo   - Press Ctrl+C in the server terminal, OR
            echo   - scripts\stop_server.bat
            echo   Then run: set HAJIMI_RECREATE_VENV=1 ^&^& scripts\setup_server_env.bat
            exit /b 1
        )
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
    echo [HAJIMI-L5] server\.venv exists ¡ª refresh dependencies.
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
echo [HAJIMI-L5] Purging stale FastAPI package layout...
"%VENV_PY%" -m pip uninstall -y fastapi starlette >nul 2>&1
if exist "%FASTAPI_SITE%\_compat" (
    echo [HAJIMI-L5] Removing orphaned fastapi/_compat/ directory ...
    rmdir /s /q "%FASTAPI_SITE%\_compat" 2>nul
)
if exist "%FASTAPI_SITE%\_compat.py" del /f /q "%FASTAPI_SITE%\_compat.py" 2>nul
echo [HAJIMI-L5] Aligning FastAPI core stack (fastapi/starlette/pydantic)...
"%VENV_PY%" -m pip install --force-reinstall "fastapi==0.115.0" "starlette==0.38.6" "pydantic==2.9.2" "pydantic-settings==2.6.1" "typing-extensions>=4.8.0"
if errorlevel 1 (
    echo [HAJIMI-L5] ERROR: FastAPI core stack install failed
    exit /b 1
)
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

:verify
echo [HAJIMI-L5] Verifying installation...
"%VENV_PY%" -c "from fastapi import FastAPI; import fastapi, uvicorn, pydantic, sqlalchemy, psutil; print('ok fastapi', fastapi.__version__)"
if errorlevel 1 (
    if "!_HAJIMI_VERIFY_RETRIED!"=="0" (
        echo [HAJIMI-L5] Verification failed ¡ª retrying with full venv recreate ...
        set _HAJIMI_VERIFY_RETRIED=1
        set HAJIMI_RECREATE_VENV=1
        goto begin
    )
    echo [HAJIMI-L5] ERROR: venv verification failed
    echo [HAJIMI-L5] Try: set HAJIMI_RECREATE_VENV=1 ^&^& scripts\setup_server_env.bat
    echo [HAJIMI-L5] Or:  scripts\repair_l5_venv.bat
    exit /b 1
)

echo.
echo [HAJIMI-L5] Done. Start L5 Sidecar with: scripts\start_server.bat
endlocal
exit /b 0
