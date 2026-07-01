@echo off
setlocal EnableExtensions

if not defined OMNI_ROOT set "OMNI_ROOT=E:\Tools\OmniParser"
set "OMNI_SERVER=%OMNI_ROOT%\omnitool\omniparserserver"
set "OMNI_HOST=127.0.0.1"
if not defined OMNI_PORT set "OMNI_PORT=8002"

if not defined OMNI_PY set "OMNI_PY=E:\CodingSoftwards\Anaconda\envs\omni\python.exe"
if not exist "%OMNI_PY%" (
    for /f "delims=" %%B in ('conda info --base 2^>nul') do set "OMNI_PY=%%B\envs\omni\python.exe"
)

rem If omniparserserver is already up, do not start a second instance
"%OMNI_PY%" -c "import urllib.request; urllib.request.urlopen('http://%OMNI_HOST%:%OMNI_PORT%/probe/', timeout=2)" >nul 2>&1
if not errorlevel 1 (
    echo [OmniParser] Already running at http://%OMNI_HOST%:%OMNI_PORT%/
    echo [OmniParser] CPU parse takes ~2-4 min per screenshot. Do NOT click inspect again while parsing.
    echo [OmniParser] If inspect failed, wait for current parse to finish before retrying.
    endlocal
    exit /b 0
)

if not exist "%OMNI_SERVER%" (
    echo [ERROR] OmniParser server dir not found:
    echo   %OMNI_SERVER%
    echo Run scripts\setup_omniparser.bat first.
    exit /b 1
)

if not exist "%OMNI_PY%" (
    echo [ERROR] conda env omni not found: %OMNI_PY%
    exit /b 1
)

if not exist "%OMNI_ROOT%\weights\icon_detect\model.pt" (
    echo [ERROR] Weights missing under %OMNI_ROOT%\weights
    exit /b 1
)

cd /d "%~dp0.."
"%OMNI_PY%" scripts\patch_omniparser.py
"%OMNI_PY%" scripts\check_port.py %OMNI_HOST% %OMNI_PORT%
if errorlevel 1 (
    echo [ERROR] Port %OMNI_PORT% is in use but /probe/ did not respond.
    echo   Find process: netstat -ano ^| findstr ":%OMNI_PORT%"
    echo   Kill it:     taskkill /F /PID ^<pid^>
    echo   Or use another port: set OMNI_PORT=8003 ^&^& scripts\start_omniparser.bat
    exit /b 1
)

set "CUDA_VISIBLE_DEVICES="
set "OMNIPARSER_MAX_SIDE=960"
set "OMNIPARSER_BATCH_SIZE=8"
cd /d "%OMNI_SERVER%"

echo [OmniParser] Starting http://%OMNI_HOST%:%OMNI_PORT% (CPU mode) ...
echo [OmniParser] Press Ctrl+C to stop.
"%OMNI_PY%" -m omniparserserver --som_model_path ../../weights/icon_detect/model.pt --caption_model_name florence2 --caption_model_path ../../weights/icon_caption_florence --device cpu --BOX_TRESHOLD 0.05 --host %OMNI_HOST% --port %OMNI_PORT%

endlocal
exit /b %ERRORLEVEL%
