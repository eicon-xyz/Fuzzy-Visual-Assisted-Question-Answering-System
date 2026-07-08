@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call start_mock.bat
exit /b %ERRORLEVEL%
