@echo off
setlocal EnableExtensions
cd /d %~dp0..

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

"%PYTHON%" scripts\check_gpu_api_tunnel.py
if errorlevel 1 exit /b 1

set OMNIPARSER_URL=http://127.0.0.1:9800
set OMNIPARSER_TIMEOUT=30
"%PYTHON%" test_parse_local.py %*
endlocal
exit /b %ERRORLEVEL%
