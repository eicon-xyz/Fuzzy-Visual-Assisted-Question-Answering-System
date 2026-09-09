@echo off
cd /d %~dp0..

set "CLIENT_PY="
if defined VIDEO_RAG_PY if exist "%VIDEO_RAG_PY%" set "CLIENT_PY=%VIDEO_RAG_PY%"
if not defined CLIENT_PY if defined PYTHON if exist "%PYTHON%" set "CLIENT_PY=%PYTHON%"
if not defined CLIENT_PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined CLIENT_PY set "CLIENT_PY=%%P"
    )
)
if not defined CLIENT_PY (
    for /f "delims=" %%B in ('conda info --base 2^>nul') do (
        if exist "%%B\envs\videorag\python.exe" set "CLIENT_PY=%%B\envs\videorag\python.exe"
    )
)

if defined CLIENT_PY (
    "%CLIENT_PY%" scripts\check_ui_env.py >nul 2>&1
    if not errorlevel 1 exit /b 0
)

echo [HAJIMI] First run: B-end UI missing PyQt5 - auto install (about 1-3 min) ...
echo [HAJIMI] After install the UI will start. For videorag: conda activate videorag ^&^& pip install -r requirements.txt

call "%~dp0setup.bat"
if errorlevel 1 exit /b 1

set "VIDEO_RAG_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VIDEO_RAG_PY%" (
    echo [HAJIMI] ERROR: .venv python not found after setup.bat
    exit /b 1
)

"%VIDEO_RAG_PY%" scripts\check_ui_env.py
exit /b %ERRORLEVEL%
