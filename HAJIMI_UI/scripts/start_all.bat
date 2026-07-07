@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
set HAJIMI_API_URL=http://127.0.0.1:%HAJIMI_PORT%

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python
) else (
    set PYTHON=python
)

set "DEPLOY_MODE=gpu_api"
for /f "delims=" %%M in ('"%PYTHON%" -c "import json,os; p=os.path.join(os.environ.get('LOCALAPPDATA',''),'HAJIMI','user_settings.json'); d=json.load(open(p,encoding='utf-8')) if os.path.isfile(p) else {}; print(d.get('deployment_mode','gpu_api'))" 2^>nul') do set "DEPLOY_MODE=%%M"

if /i "%DEPLOY_MODE%"=="gpu_api" (
    echo [HAJIMI] deployment_mode=gpu_api — use GPU API :9800, NOT local CPU :8002
    echo [HAJIMI] inspect ~2-5s via SSH tunnel. If tunnel down, run scripts\start_gpu_one_click.bat
    call "%~dp0stop_all.bat"
    call "%~dp0start_gpu_api_demo.bat"
    endlocal
    exit /b %ERRORLEVEL%
)

echo [HAJIMI] deployment_mode=%DEPLOY_MODE% — local OmniParser CPU path
echo [HAJIMI] Step 1/2: stop stale backend on :%HAJIMI_PORT% and :8002 ...
call "%~dp0stop_all.bat"

echo [HAJIMI] Step 2/2: start OmniParser + A-end :%HAJIMI_PORT% + B-end ...
timeout /t 2 /nobreak >nul

start "HAJIMI-OmniParser" cmd /k "%~dp0start_omniparser.bat"
timeout /t 3 /nobreak >nul
start "HAJIMI-A-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& %~dp0start_server.bat"
timeout /t 2 /nobreak >nul
start "HAJIMI-L5-Sidecar" cmd /k "set L5_API_PORT=8011&& %~dp0start_l5_sidecar.bat"
timeout /t 2 /nobreak >nul
start "HAJIMI-B-end" cmd /k "set HAJIMI_PORT=%HAJIMI_PORT%&& set HAJIMI_API_URL=%HAJIMI_API_URL%&& %~dp0start_client.bat"

echo [HAJIMI] Launched. A-end :%HAJIMI_PORT% + L5 Sidecar :8011 — wait for Omniparser initialized.
endlocal
exit /b %ERRORLEVEL%
