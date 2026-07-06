@echo off
setlocal EnableExtensions

call "%~dp0resolve_omni_root.bat"
if not "%OMNI_ROOT_RESOLVED%"=="1" (
    echo [ERROR] OmniParser not found.
    echo   Set OMNI_ROOT to your OmniParser install, or clone weights into:
    echo   %~dp0..\OmniParser
    echo   Run scripts\setup_omniparser.bat for first-time setup.
    exit /b 1
)

set "OMNI_SERVER=%OMNI_ROOT%\omnitool\omniparserserver"
set "OMNI_HOST=127.0.0.1"
if not defined OMNI_PORT set "OMNI_PORT=8002"

set "OMNI_PY="
if defined OMNI_PY if exist "%OMNI_PY%" goto :have_omni_py
if defined PYTHON if exist "%PYTHON%" set "OMNI_PY=%PYTHON%" & goto :have_omni_py
for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined OMNI_PY set "OMNI_PY=%%P"
)
if defined OMNI_PY goto :have_omni_py
for /f "delims=" %%B in ('conda info --base 2^>nul') do (
    if exist "%%B\envs\omni\python.exe" set "OMNI_PY=%%B\envs\omni\python.exe"
)
:have_omni_py

if not defined OMNI_PY (
    echo [ERROR] Python not found for OmniParser.
    echo   Activate your venv/conda env, or: set OMNI_PY=C:\path\to\python.exe
    exit /b 1
)

"%OMNI_PY%" -c "import urllib.request; urllib.request.urlopen('http://%OMNI_HOST%:%OMNI_PORT%/probe/', timeout=2)" >nul 2>&1
if not errorlevel 1 (
    echo [OmniParser] Already running at http://%OMNI_HOST%:%OMNI_PORT%/
    echo [OmniParser] CPU parse takes ~2-4 min per screenshot. Do NOT click inspect again while parsing.
    endlocal
    exit /b 0
)

if not exist "%OMNI_SERVER%" (
    echo [ERROR] OmniParser server dir not found:
    echo   %OMNI_SERVER%
    echo Run scripts\setup_omniparser.bat first.
    exit /b 1
)

if not exist "%OMNI_ROOT%\weights\icon_detect\model.pt" (
    echo [ERROR] Weights missing under %OMNI_ROOT%\weights
    exit /b 1
)

cd /d "%~dp0.."
set "OMNI_ROOT=%OMNI_ROOT%"
"%OMNI_PY%" scripts\patch_omniparser.py
"%OMNI_PY%" scripts\check_port.py %OMNI_HOST% %OMNI_PORT%
if errorlevel 1 (
    echo [ERROR] Port %OMNI_PORT% is in use but /probe/ did not respond.
    exit /b 1
)

set "CUDA_VISIBLE_DEVICES="
set "PYTHONNOUSERSITE=1"
set "OMNIPARSER_MAX_SIDE=960"
set "OMNIPARSER_BATCH_SIZE=8"

set "OMNI_DEVICE=cpu"
set "_OMNI_DEV_FILE=%TEMP%\hajimi_omni_device.txt"
"%OMNI_PY%" "%~dp0detect_omni_device.py" 1>"%_OMNI_DEV_FILE%"
if exist "%_OMNI_DEV_FILE%" set /p OMNI_DEVICE=<"%_OMNI_DEV_FILE%"
if not defined OMNI_DEVICE set "OMNI_DEVICE=cpu"

cd /d "%OMNI_SERVER%"

if /i "%OMNI_DEVICE%"=="cpu" (
    echo [OmniParser] CPU mode — parse ~2-4 min per screenshot.
)
echo [OmniParser] Starting http://%OMNI_HOST%:%OMNI_PORT% (%OMNI_DEVICE% mode) ...
"%OMNI_PY%" -m omniparserserver --som_model_path ../../weights/icon_detect/model.pt --caption_model_name florence2 --caption_model_path ../../weights/icon_caption_florence --device %OMNI_DEVICE% --BOX_TRESHOLD 0.05 --host %OMNI_HOST% --port %OMNI_PORT%

endlocal
exit /b %ERRORLEVEL%
