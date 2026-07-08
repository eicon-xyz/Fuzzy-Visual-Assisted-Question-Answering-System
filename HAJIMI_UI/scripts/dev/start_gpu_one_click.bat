@echo off
setlocal EnableExtensions
cd /d %~dp0\..
call start_gpu_one_click.bat
endlocal
exit /b %ERRORLEVEL%
