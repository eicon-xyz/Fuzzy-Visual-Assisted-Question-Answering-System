@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call start_mock.bat
endlocal
exit /b %ERRORLEVEL%
