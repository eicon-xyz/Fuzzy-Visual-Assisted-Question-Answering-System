@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0..

set VENV_PY=server\.venv\Scripts\python.exe
set VENV_PIP=server\.venv\Scripts\python.exe -m pip

REM --- Optional force recreate: set HAJIMI_RECREATE_VENV=1 ---
if /I "%HAJIMI_RECREATE_VENV%"=="1" (
    echo [HAJIMI] Force recreate requested.
    call "%~dp0stop_server_hint.bat"
    if exist server\.venv (
        echo [HAJIMI] Removing server\.venv ...
        rmdir /s /q server\.venv 2>nul
        if exist server\.venv (
            echo [HAJIMI] ERROR: Cannot remove server\.venv — stop A-end server first:
            echo   - Press Ctrl+C in the server terminal, OR
            echo   - scripts\stop_server.bat
            echo   Then run: set HAJIMI_RECREATE_VENV=1 ^&^& scripts\setup_server_env.bat
            exit /b 1
        )
    )
)

if exist "%VENV_PY%" (
    echo [HAJIMI] server\.venv already exists — skip create, refresh dependencies.
    goto install_deps
)

echo [HAJIMI] Creating isolated server virtual environment...
python -m venv server\.venv
if errorlevel 1 (
    echo.
    echo [HAJIMI] ERROR: failed to create server\.venv
    echo [HAJIMI] Common fixes:
    echo   1. Stop A-end if running: scripts\stop_server.bat
    echo   2. Close other terminals using server\.venv
    echo   3. Delete folder manually: rmdir /s /q server\.venv
    echo   4. Retry: scripts\setup_server_env.bat
    echo   Or reuse existing venv if present — start_server.bat works without re-setup.
    exit /b 1
)

:install_deps
echo [HAJIMI] Installing server dependencies into server\.venv ...
REM Temporarily disable Windows IE proxy (127.0.0.1:7890) when Clash/V2Ray is off — pip uses it otherwise
set "_HAJIMI_PROXY_ENABLE="
for /f "tokens=3" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2^>nul ^| findstr ProxyEnable') do set "_HAJIMI_PROXY_ENABLE=%%A"
if /I "%_HAJIMI_PROXY_ENABLE%"=="0x1" (
    echo [HAJIMI] Disabling IE proxy for pip install ^(will restore after^) ...
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
    echo [HAJIMI] ERROR: pip install failed
    exit /b 1
)

echo [HAJIMI] Verifying installation...
"%VENV_PY%" -c "import fastapi, uvicorn, pydantic, sqlalchemy, psutil; print('fastapi', fastapi.__version__, 'sqlalchemy', sqlalchemy.__version__, 'psutil', psutil.__version__)"
if errorlevel 1 (
    echo [HAJIMI] ERROR: venv verification failed. Try:
    echo   set HAJIMI_RECREATE_VENV=1
    echo   scripts\setup_server_env.bat
    exit /b 1
)

echo.
echo [HAJIMI] Done. Start A-end with: scripts\start_server.bat
echo [HAJIMI] PyQt client can stay in videorag — no need to install server deps there.
