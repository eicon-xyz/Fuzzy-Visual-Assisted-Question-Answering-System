@echo off
rem Sets RESOLVED_PYTHON to a usable python.exe (no author-path hardcoding).
rem Optional overrides: VIDEO_RAG_PY, OMNI_PY, PYTHON
if defined VIDEO_RAG_PY if exist "%VIDEO_RAG_PY%" (
    set "RESOLVED_PYTHON=%VIDEO_RAG_PY%"
    goto :done
)
if defined OMNI_PY if exist "%OMNI_PY%" (
    set "RESOLVED_PYTHON=%OMNI_PY%"
    goto :done
)
if defined PYTHON (
    where "%PYTHON%" >nul 2>&1
    if not errorlevel 1 (
        set "RESOLVED_PYTHON=%PYTHON%"
        goto :done
    )
)
where python >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('where python 2^>nul ^| findstr /i /v "WindowsApps"') do (
        set "RESOLVED_PYTHON=%%P"
        goto :done
    )
)
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" (
    set "RESOLVED_PYTHON=%CONDA_PREFIX%\python.exe"
    goto :done
)
for /f "delims=" %%B in ('conda info --base 2^>nul') do (
    if exist "%%B\envs\videorag\python.exe" set "RESOLVED_PYTHON=%%B\envs\videorag\python.exe"
)
:done
if not defined RESOLVED_PYTHON (
    echo [ERROR] Python not found. Activate a venv or set PYTHON=path\to\python.exe
    exit /b 1
)
