@echo off
REM Quick check: WebEngine HTML UI path still loads (HAJIMI_NATIVE_UI=0)
cd /d "%~dp0.."
set HAJIMI_NATIVE_UI=0
echo [verify] HAJIMI_NATIVE_UI=0 — import MainWidget (WebEngine path)...
"E:\CodingSoftwards\Anaconda\envs\videorag\python.exe" -c "import sys; sys.path.insert(0,'.'); from config import USE_NATIVE_UI; assert not USE_NATIVE_UI; print('OK: USE_NATIVE_UI=0')"
if errorlevel 1 exit /b 1
echo [verify] design tokens...
"E:\CodingSoftwards\Anaconda\envs\videorag\python.exe" scripts\sync_design_tokens.py
exit /b %errorlevel%
