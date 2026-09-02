@echo off
setlocal EnableExtensions
cd /d %~dp0..

set "VENV_PY=server\.venv\Scripts\python.exe"
set "NEED_SETUP=0"

if not exist "%VENV_PY%" (
    set "NEED_SETUP=1"
) else (
    "%VENV_PY%" -c "import fastapi, uvicorn, sqlalchemy, psutil" >nul 2>&1
    if errorlevel 1 set "NEED_SETUP=1"
)

if "%NEED_SETUP%"=="1" (
    echo [HAJIMI] First run: configuring 8010 A-end environment ^(about 1-3 min^) ...
    call "%~dp0setup_server_env.bat"
    if errorlevel 1 (
        endlocal
        exit /b 1
    )
)

if not exist "server\.env" (
    if exist "server\.env.example" (
        copy /y "server\.env.example" "server\.env" >nul
        echo [HAJIMI] WARN: created server\.env from example ¡ª fill LLM_API_KEY if needed.
    )
)

if not exist "%VENV_PY%" (
    echo [HAJIMI] ERROR: server\.venv still missing after setup.
    endlocal
    exit /b 1
)

"%VENV_PY%" -c "import fastapi, uvicorn, sqlalchemy, psutil" >nul 2>&1
if errorlevel 1 (
    echo [HAJIMI] ERROR: 8010 server deps verification failed. Retry: scripts\setup_server_env.bat
    endlocal
    exit /b 1
)

endlocal
exit /b 0
