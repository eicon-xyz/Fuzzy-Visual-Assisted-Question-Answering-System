@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

echo [HAJIMI] Starting B-end client (A-end: %HAJIMI_API_URL%) ...

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

if not defined CLIENT_PY (
    echo [ERROR] Python not found.
    echo   Run from an activated venv, or: set VIDEO_RAG_PY=C:\path\to\python.exe
    echo   Or directly: python main.py
    exit /b 1
)

echo [HAJIMI] Using %CLIENT_PY%
"%CLIENT_PY%" main.py
endlocal
exit /b %ERRORLEVEL%
