@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call start_gpu_one_click.bat
exit /b %ERRORLEVEL%
