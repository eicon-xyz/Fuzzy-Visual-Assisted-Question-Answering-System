@echo off
setlocal EnableExtensions

if not defined OMNI_PY (
    for /f "delims=" %%B in ('conda info --base 2^>nul') do set "OMNI_PY=%%B\envs\omni\python.exe"
)

if not exist "%OMNI_PY%" (
    echo [ERROR] conda env omni not found. Run scripts\setup_omniparser.bat first.
    exit /b 1
)

echo [upgrade] Installing PyTorch cu128 for RTX 50 / Blackwell (sm_120) ...
call conda run -n omni pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 exit /b 1

echo [upgrade] Verifying CUDA arch list ...
"%OMNI_PY%" -c "import torch; print('cuda:', torch.cuda.is_available()); print('arch:', torch.cuda.get_arch_list())"
echo.
echo Done. Re-run scripts\start_omniparser.bat — should show cuda mode if kernel test passes.
echo To force cuda: set OMNI_FORCE_CUDA=1 ^&^& scripts\start_omniparser.bat

endlocal
exit /b 0
