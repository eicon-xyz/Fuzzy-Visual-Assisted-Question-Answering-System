@echo off
setlocal EnableExtensions
cd /d %~dp0..

if defined HAJIMI_L5_ROOT (
    set "L5_ROOT=%HAJIMI_L5_ROOT%"
) else (
    set "L5_ROOT=%~dp0..\..\new_JIMI\HAJIMI_UI"
)

if not exist "%L5_ROOT%\scripts\start_server.bat" (
    echo [HAJIMI] ERROR: L5 Sidecar not found at:
    echo   %L5_ROOT%
    echo Set HAJIMI_L5_ROOT to new_JIMI\HAJIMI_UI if using a custom path.
    endlocal
    exit /b 1
)

set "L5_VENV=%L5_ROOT%\server\.venv\Scripts\python.exe"
set "NEED_SETUP=0"

if not exist "%L5_VENV%" (
    set "NEED_SETUP=1"
) else (
    "%L5_VENV%" -c "import fastapi, uvicorn, sqlalchemy, psutil" >nul 2>&1
    if errorlevel 1 set "NEED_SETUP=1"
)

if "%NEED_SETUP%"=="1" (
    echo [HAJIMI] First run: configuring 8011 L5 Sidecar environment ^(about 1-3 min^) ...
    echo [HAJIMI] L5 venv path: %L5_ROOT%\server\.venv
    pushd "%L5_ROOT%"
    call scripts\setup_server_env.bat
    set "SETUP_ERR=%ERRORLEVEL%"
    popd
    if not "%SETUP_ERR%"=="0" (
        endlocal
        exit /b 1
    )
)

if not exist "%L5_ROOT%\server\.env" (
    if exist "%L5_ROOT%\server\.env.example" (
        copy /y "%L5_ROOT%\server\.env.example" "%L5_ROOT%\server\.env" >nul
        echo [HAJIMI] WARN: created L5 server\.env from example — set OMNIPARSER_URL=http://127.0.0.1:9800
    )
)

if not exist "%L5_VENV%" (
    echo [HAJIMI] ERROR: L5 server\.venv still missing after setup.
    endlocal
    exit /b 1
)

"%L5_VENV%" -c "import fastapi, uvicorn, sqlalchemy, psutil" >nul 2>&1
if errorlevel 1 (
    echo [HAJIMI] ERROR: 8011 L5 deps verification failed at %L5_ROOT%\server\.venv
    echo [HAJIMI] This is NOT HAJIMI_UI\server\.venv — run setup in new_JIMI\HAJIMI_UI
    endlocal
    exit /b 1
)

endlocal
exit /b 0
