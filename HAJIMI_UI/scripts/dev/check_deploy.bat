@echo off
setlocal EnableExtensions
cd /d %~dp0\..
call check_deploy.bat
endlocal
exit /b %ERRORLEVEL%
