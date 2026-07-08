@echo off
setlocal EnableExtensions
cd /d %~dp0..\..

echo [HAJIMI] CPU 降级模式 — 本机 OmniParser :8002 + 8010 + 8011 + UI
echo [HAJIMI] 无校园网/GPU 时使用；默认请用根目录 启动本地.bat

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

call scripts\ensure_ui_env.bat
if errorlevel 1 exit /b 1
call scripts\ensure_server_env.bat
if errorlevel 1 exit /b 1
call scripts\ensure_l5_sidecar_env.bat
if errorlevel 1 exit /b 1

"%PYTHON%" scripts\apply_local_cpu_settings.py
if errorlevel 1 exit /b 1

call scripts\start_all.bat
endlocal
exit /b %ERRORLEVEL%
