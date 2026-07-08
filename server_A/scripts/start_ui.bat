@echo off
setlocal EnableExtensions
cd /d %~dp0..
call "%~dp0_resolve_python.bat"
if errorlevel 1 exit /b 1
"%RESOLVED_PYTHON%" main.py
endlocal
exit /b %ERRORLEVEL%
