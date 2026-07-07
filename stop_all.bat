@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call stop_all.bat
endlocal
exit /b %ERRORLEVEL%
