@echo off

setlocal EnableExtensions

cd /d %~dp0..



if not defined HAJIMI_PORT set HAJIMI_PORT=8010

if not defined HAJIMI_HOST set HAJIMI_HOST=127.0.0.1



if exist server\.venv\Scripts\python.exe (

    set PYTHON=server\.venv\Scripts\python

) else (

    set PYTHON=python

    echo [HAJIMI] WARN: server\.venv not found. Run scripts\setup_server_env.bat first.

)



echo [HAJIMI] Freeing port %HAJIMI_PORT% (kill stale A-end / uvicorn reload workers) ...

"%PYTHON%" scripts\kill_port.py %HAJIMI_PORT%

if errorlevel 1 (

    echo [HAJIMI] WARN: port %HAJIMI_PORT% may still be in use. Close HAJIMI-A-end cmd windows manually.

)



echo [HAJIMI] Checking A-end server dependencies...

"%PYTHON%" -c "import fastapi, uvicorn" 2>nul

if errorlevel 1 (

    echo [HAJIMI] Missing fastapi/uvicorn — run scripts\setup_server_env.bat

    exit /b 1

)



echo [HAJIMI] Starting A-end on http://%HAJIMI_HOST%:%HAJIMI_PORT% (no --reload, single process) ...

echo [HAJIMI] B-end: set HAJIMI_API_URL=http://%HAJIMI_HOST%:%HAJIMI_PORT%

"%PYTHON%" -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%

endlocal

exit /b %ERRORLEVEL%

