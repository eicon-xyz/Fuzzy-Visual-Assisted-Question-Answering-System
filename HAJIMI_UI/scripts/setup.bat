@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not exist .venv\Scripts\python.exe (
    echo [HAJIMI] Creating .venv ...
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

echo [HAJIMI] Installing B-end UI dependencies ...
.venv\Scripts\python -m pip install -U pip -q
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 exit /b 1

.venv\Scripts\python scripts\check_ui_env.py
if errorlevel 1 exit /b 1

echo.
echo [OK] Setup complete.
echo Next: run scripts\start_local_vision.bat or the root fullstack bat
echo L5 env: server_A\server\.env must contain DEEPSEEK_API_KEY / LLM settings
endlocal
exit /b 0
