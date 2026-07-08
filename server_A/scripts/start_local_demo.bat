@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo [HAJIMI] Local demo mode — OmniParser will use CPU (OMNI_FORCE_CPU=1)
set OMNI_FORCE_CPU=1

if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

"%PYTHON%" scripts\probe_campus_warn.py
if errorlevel 1 (
    echo [HAJIMI] Continuing with local CPU demo anyway ...
)

call "%~dp0start_all.bat"
endlocal
