@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\stop_all.bat
endlocal
exit /b %ERRORLEVEL%
