@echo off
rem Resolve OMNI_ROOT: env > repo (server+weights) > E:\Tools > repo (server only)
set "OMNI_ROOT_RESOLVED=0"
set "REPO_ROOT=%~dp0..\OmniParser"
set "TOOLS_ROOT=E:\Tools\OmniParser"

if defined OMNI_ROOT (
    if exist "%OMNI_ROOT%\omnitool\omniparserserver" (
        set "OMNI_ROOT_RESOLVED=1"
        goto :done
    )
    echo [WARN] OMNI_ROOT is set but invalid: %OMNI_ROOT%
)

if exist "%REPO_ROOT%\omnitool\omniparserserver" if exist "%REPO_ROOT%\weights\icon_detect\model.pt" (
    set "OMNI_ROOT=%REPO_ROOT%"
    set "OMNI_ROOT_RESOLVED=1"
    goto :done
)

if exist "%TOOLS_ROOT%\omnitool\omniparserserver" (
    set "OMNI_ROOT=%TOOLS_ROOT%"
    set "OMNI_ROOT_RESOLVED=1"
    goto :done
)

if exist "%REPO_ROOT%\omnitool\omniparserserver" (
    set "OMNI_ROOT=%REPO_ROOT%"
    set "OMNI_ROOT_RESOLVED=1"
    goto :done
)

set "OMNI_ROOT="
set "OMNI_ROOT_RESOLVED=0"
:done
