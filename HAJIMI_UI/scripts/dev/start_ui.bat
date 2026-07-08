@echo off
setlocal EnableExtensions
cd /d %~dp0\..
call start_client.bat
endlocal
exit /b %ERRORLEVEL%
