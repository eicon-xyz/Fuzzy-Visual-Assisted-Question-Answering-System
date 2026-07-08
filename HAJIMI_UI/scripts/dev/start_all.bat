@echo off
setlocal EnableExtensions
cd /d %~dp0\..
call start_all.bat
endlocal
exit /b %ERRORLEVEL%
