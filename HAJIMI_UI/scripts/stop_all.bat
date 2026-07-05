@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python
) else (
    set PYTHON=python
)

echo [HAJIMI] Stopping A-end :%HAJIMI_PORT% ...
"%PYTHON%" scripts\kill_port.py %HAJIMI_PORT%

echo [HAJIMI] Done. Close empty HAJIMI cmd windows if any remain.
endlocal
