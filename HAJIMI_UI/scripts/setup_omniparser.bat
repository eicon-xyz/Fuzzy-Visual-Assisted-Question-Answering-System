@echo off
setlocal EnableExtensions

call "%~dp0resolve_omni_root.bat"
if not defined OMNI_PY set "OMNI_PY=E:\CodingSoftwards\Anaconda\envs\omni\python.exe"
if not defined OMNI_MS set "OMNI_MS=E:\CodingSoftwards\Anaconda\envs\omni\Scripts\modelscope.exe"

if not exist "%OMNI_ROOT%" (
    echo [1/5] Cloning OmniParser to %OMNI_ROOT% ...
    if not exist "E:\Tools" mkdir "E:\Tools"
    git clone --depth 1 https://github.com/microsoft/OmniParser.git "%OMNI_ROOT%"
    if errorlevel 1 exit /b 1
) else (
    echo [1/5] OmniParser already at %OMNI_ROOT%
)

echo [2/5] Creating conda env omni (python 3.12) ...
call conda create -n omni python=3.12 -y
if errorlevel 1 exit /b 1

for /f "delims=" %%B in ('conda info --base 2^>nul') do (
    set "OMNI_PY=%%B\envs\omni\python.exe"
    set "OMNI_MS=%%B\envs\omni\Scripts\modelscope.exe"
)

echo [3/5] Installing PyTorch and requirements ...
rem Default cu124 does NOT support RTX 50 (sm_120). start_omniparser.bat will force CPU.
rem For local RTX 50 GPU: run scripts\upgrade_omni_pytorch_cu128.bat after setup.
call conda run -n omni pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
call conda run -n omni pip install -r "%OMNI_ROOT%\requirements.txt" fastapi uvicorn transformers==4.48.3
if errorlevel 1 exit /b 1

echo [4/5] Downloading weights via ModelScope (may take several minutes) ...
"%OMNI_MS%" download --model AI-ModelScope/OmniParser-v2.0 --local_dir "%OMNI_ROOT%\weights"
"%OMNI_MS%" download --model AI-ModelScope/Florence-2-base --local_dir "%OMNI_ROOT%\weights\florence2_base"
if errorlevel 1 exit /b 1

if exist "%OMNI_ROOT%\weights\icon_caption" (
    if not exist "%OMNI_ROOT%\weights\icon_caption_florence" (
        move "%OMNI_ROOT%\weights\icon_caption" "%OMNI_ROOT%\weights\icon_caption_florence"
    )
)

echo [5/5] Copying Florence-2 helper files ...
for %%F in (configuration_florence2.py modeling_florence2.py processing_florence2.py preprocessor_config.json tokenizer.json tokenizer_config.json vocab.json) do (
    if exist "%OMNI_ROOT%\weights\florence2_base\%%F" (
        copy /Y "%OMNI_ROOT%\weights\florence2_base\%%F" "%OMNI_ROOT%\weights\icon_caption_florence\%%F" >nul
    )
)

echo.
echo Done. Next: scripts\start_omniparser.bat  (RTX 50 auto CPU; campus GPU: b_group2_intranet_setup.py)
echo Optional GPU on RTX 50: scripts\upgrade_omni_pytorch_cu128.bat
echo Then:  scripts\start_server.bat

endlocal
exit /b 0
