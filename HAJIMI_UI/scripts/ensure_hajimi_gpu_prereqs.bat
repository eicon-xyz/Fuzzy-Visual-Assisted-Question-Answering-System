@echo off
setlocal EnableExtensions

echo.
echo [HAJIMI] Environment check [0/5] — 8010 venv / 8011 L5 / B UI ^(first run may take a few minutes^)
echo.

call "%~dp0ensure_server_env.bat"
if errorlevel 1 exit /b 1

call "%~dp0ensure_l5_sidecar_env.bat"
if errorlevel 1 exit /b 1

call "%~dp0ensure_ui_env.bat"
if errorlevel 1 exit /b 1

endlocal
exit /b 0
