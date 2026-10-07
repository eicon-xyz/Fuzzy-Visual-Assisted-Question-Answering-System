@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined L5_API_PORT set L5_API_PORT=8011

call "%~dp0_resolve_l5_root.bat"
set "L5_PY=%L5_ROOT%\server\.venv\Scripts\python.exe"
if not exist "%L5_PY%" set "L5_PY=python"

echo [HAJIMI] Stopping L5 Sidecar :%L5_API_PORT% ...
"%L5_PY%" "%~dp0kill_port.py" %L5_API_PORT%

echo [HAJIMI] Done. Close empty HAJIMI cmd windows if any remain.
endlocal
exit /b 0
