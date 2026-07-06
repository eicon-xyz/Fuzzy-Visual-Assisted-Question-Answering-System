@echo off
setlocal EnableExtensions
cd /d %~dp0

set HAJIMI_PORT=8010
set HAJIMI_HOST=127.0.0.1
set HAJIMI_API_URL=http://%HAJIMI_HOST%:%HAJIMI_PORT%
set OMNI_ROOT=%~dp0OmniParser
set OMNI_PORT=8002
set OMNI_SERVER=%OMNI_ROOT%\omnitool\omniparserserver
set OMNI_PY=C:\Users\86178\.conda\envs\omni\python.exe
set VENV_PY=%~dp0server\.venv\Scripts\python.exe

echo ============================================
echo  HAJIMI Startup
echo  OmniPython: %OMNI_PY%
echo  VenvPython: %VENV_PY%
echo  OmniServer: %OMNI_SERVER%
echo  A-end: %HAJIMI_API_URL%
echo ============================================

echo [1/5] Cleaning ports ...
%VENV_PY% -c "import subprocess,re;out=subprocess.check_output(['netstat','-ano'],text=True);pids=set();[pids.add(l.strip().split()[-1]) for l in out.splitlines() if any(p in l and 'LISTENING' in l for p in [':8002 ',':8010 '])];[subprocess.run(['taskkill','/F','/T','/PID',p],capture_output=True) for p in pids];print('killed',len(pids))"
timeout /t 2 /nobreak >nul

echo [2/5] Verifying ...
if not exist "%OMNI_SERVER%\omniparserserver.py" (
    echo [ERROR] OmniParser not found: %OMNI_SERVER%
    pause
    exit /b 1
)

echo [3/5] Starting OmniParser on :%OMNI_PORT% ...
start "HAJIMI-OmniParser" cmd /k "cd /d %OMNI_SERVER% && %OMNI_PY% -m omniparserserver --som_model_path ../../weights/icon_detect/model.pt --caption_model_name florence2 --caption_model_path ../../weights/icon_caption_florence --device cpu --BOX_TRESHOLD 0.05 --host %HAJIMI_HOST% --port %OMNI_PORT%"
timeout /t 5 /nobreak >nul

echo [4/5] Starting A-end on %HAJIMI_API_URL% ...
start "HAJIMI-A-end" cmd /k "cd /d %~dp0 && %VENV_PY% -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%"

echo [5/5] Waiting for A-end ...
:wait_a_end
timeout /t 3 /nobreak >nul
%VENV_PY% -c "import urllib.request; urllib.request.urlopen('http://%HAJIMI_HOST%:%HAJIMI_PORT%/api/demo/health', timeout=3)" >nul 2>&1
if errorlevel 1 goto :wait_a_end

echo [5/5] Launching B-end ...
start "HAJIMI-B-end" cmd /k "cd /d %~dp0 && set HAJIMI_API_URL=%HAJIMI_API_URL%&& set HAJIMI_AUTO_LAUNCH_A_END=0&& python main.py"

echo.
echo   All three windows launched.
echo   Wait for OmniParser "Omniparser initialized" before using.
endlocal
