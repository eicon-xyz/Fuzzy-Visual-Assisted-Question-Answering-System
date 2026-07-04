@echo off
REM Quick check: WebEngine HTML UI path still loads (HAJIMI_NATIVE_UI=0)
cd /d "%~dp0.."
set HAJIMI_NATIVE_UI=0
call "%~dp0_resolve_python.bat"
if errorlevel 1 exit /b 1
echo [verify] HAJIMI_NATIVE_UI=0 — import config ...
"%RESOLVED_PYTHON%" -c "import sys; sys.path.insert(0,'.'); from config import USE_NATIVE_UI; assert not USE_NATIVE_UI; print('OK: USE_NATIVE_UI=0')"
if errorlevel 1 exit /b 1
echo [verify] design tokens...
"%RESOLVED_PYTHON%" scripts\sync_design_tokens.py
exit /b %errorlevel%
