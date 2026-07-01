@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

echo [HAJIMI] Starting B-end client (A-end: %HAJIMI_API_URL%) ...

if not defined VIDEO_RAG_PY set "VIDEO_RAG_PY=E:\CodingSoftwards\Anaconda\envs\videorag\python.exe"
if not exist "%VIDEO_RAG_PY%" (
    for /f "delims=" %%B in ('conda info --base 2^>nul') do set "VIDEO_RAG_PY=%%B\envs\videorag\python.exe"
)

if not exist "%VIDEO_RAG_PY%" (
    echo [ERROR] videorag python not found: %VIDEO_RAG_PY%
    echo   Set env: set VIDEO_RAG_PY=C:\path\to\envs\videorag\python.exe
    echo   Or activate videorag manually and run: python main.py
    exit /b 1
)

echo [HAJIMI] Using %VIDEO_RAG_PY%
"%VIDEO_RAG_PY%" main.py
endlocal
exit /b %ERRORLEVEL%
