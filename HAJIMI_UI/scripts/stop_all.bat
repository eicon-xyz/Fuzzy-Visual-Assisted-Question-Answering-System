@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
if not defined L5_API_PORT set L5_API_PORT=8011
if not defined OMNI_PORT set OMNI_PORT=8002

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python
) else (
    set PYTHON=python
)

set "DEPLOY_MODE=gpu_api"
for /f "delims=" %%M in ('"%PYTHON%" -c "import json,os; p=os.path.join(os.environ.get('LOCALAPPDATA',''),'HAJIMI','user_settings.json'); d=json.load(open(p,encoding='utf-8')) if os.path.isfile(p) else {}; print(d.get('deployment_mode','gpu_api'))" 2^>nul') do set "DEPLOY_MODE=%%M"

echo [HAJIMI] Stopping A-end :%HAJIMI_PORT% ...
"%PYTHON%" scripts\kill_port.py %HAJIMI_PORT%

echo [HAJIMI] Stopping L5 Sidecar :%L5_API_PORT% ...
"%PYTHON%" scripts\kill_port.py %L5_API_PORT%

if /i "%DEPLOY_MODE%"=="gpu_api" (
    echo [HAJIMI] gpu_api mode — skip local OmniParser :%OMNI_PORT% ^(uses GPU API :9800 tunnel^)
) else (
    echo [HAJIMI] Stopping OmniParser :%OMNI_PORT% ...
    "%PYTHON%" scripts\kill_port.py %OMNI_PORT%
)

echo [HAJIMI] Done. Close empty HAJIMI cmd windows if any remain.
endlocal
