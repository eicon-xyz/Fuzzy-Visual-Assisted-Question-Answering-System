@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\start_client.bat
endlocal
exit /b %ERRORLEVEL%
