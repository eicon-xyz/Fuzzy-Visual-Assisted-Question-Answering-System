@echo off
REM Apply B-end-only proxy env from user_settings (default: disabled).
setlocal EnableExtensions
cd /d %~dp0..
set "PY=python"
if defined VIDEO_RAG_PY if exist "%VIDEO_RAG_PY%" set "PY=%VIDEO_RAG_PY%"
if defined PYTHON if exist "%PYTHON%" set "PY=%PYTHON%"
"%PY%" "%~dp0emit_proxy_env.py" > "%TEMP%\hajimi_proxy_env.bat" 2>nul
if errorlevel 1 (
    endlocal
    exit /b 0
)
endlocal & call "%TEMP%\hajimi_proxy_env.bat"
exit /b 0
