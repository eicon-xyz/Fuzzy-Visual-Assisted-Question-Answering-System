@echo off
setlocal EnableExtensions
cd /d %~dp0..
call 启动HAJIMI.bat
endlocal
exit /b %ERRORLEVEL%
