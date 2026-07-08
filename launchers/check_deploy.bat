@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call check_deploy.bat
exit /b %ERRORLEVEL%
