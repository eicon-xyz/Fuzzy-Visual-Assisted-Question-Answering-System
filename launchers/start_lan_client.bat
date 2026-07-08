@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call start_lan_client.bat
exit /b %ERRORLEVEL%
