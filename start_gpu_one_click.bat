@echo off
setlocal EnableExtensions
cd /d %~dp0HAJIMI_UI
call scripts\start_gpu_one_click.bat
endlocal
exit /b %ERRORLEVEL%
