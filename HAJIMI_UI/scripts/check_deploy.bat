@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo [HAJIMI] Ensuring local venv / UI deps (install if missing) ...
call "%~dp0ensure_hajimi_gpu_prereqs.bat"
if errorlevel 1 (
    echo [HAJIMI] Environment setup failed.
    pause
    exit /b 1
)

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
)

echo.
"%PYTHON%" scripts\check_deploy.py
set ERR=%ERRORLEVEL%
echo.
if "%ERR%"=="0" (
    echo [HAJIMI] Deploy check: all OK.
) else if "%ERR%"=="2" (
    echo [HAJIMI] Deploy check: env OK, GPU/A-end links not ready.
) else (
    echo [HAJIMI] Deploy check: environment issues — see above.
)
pause
endlocal
exit /b %ERR%
