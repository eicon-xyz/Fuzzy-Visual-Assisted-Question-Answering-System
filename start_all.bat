@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call start_all.bat
endlocal
exit /b %ERRORLEVEL%
