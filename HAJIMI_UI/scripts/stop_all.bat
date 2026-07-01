@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
if not defined OMNI_PORT set OMNI_PORT=8002

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python
) else (
    set PYTHON=python
)

echo [HAJIMI] Stopping OmniParser :%OMNI_PORT% and A-end :%HAJIMI_PORT% ...
"%PYTHON%" scripts\kill_port.py %OMNI_PORT%
"%PYTHON%" scripts\kill_port.py %HAJIMI_PORT%

echo [HAJIMI] Done. Close empty HAJIMI cmd windows if any remain.
endlocal
