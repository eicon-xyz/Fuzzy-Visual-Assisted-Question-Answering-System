@echo off
REM HAJIMI 交接验收一键脚本 — 见 HANDOFF.md §4
cd /d "%~dp0.."
call "%~dp0_resolve_python.bat"
if errorlevel 1 exit /b 1
echo.
"%RESOLVED_PYTHON%" scripts\verify_all.py %*
exit /b %errorlevel%
