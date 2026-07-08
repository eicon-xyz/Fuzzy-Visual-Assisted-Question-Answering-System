@echo off
setlocal EnableExtensions
cd /d %~dp0..\HAJIMI_UI
call scripts\check_deploy.bat
endlocal
exit /b %ERRORLEVEL%
