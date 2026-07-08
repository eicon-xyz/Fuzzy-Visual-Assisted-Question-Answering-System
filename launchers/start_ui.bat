@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call start_ui.bat
exit /b %ERRORLEVEL%
