@echo off
rem Resolve OMNI_ROOT: env > project (with weights) > E:\Tools\OmniParser
if defined OMNI_ROOT goto :done
set "REPO_ROOT=%~dp0..\OmniParser"
if exist "%REPO_ROOT%\omnitool\omniparserserver" if exist "%REPO_ROOT%\weights\icon_detect\model.pt" (
    set "OMNI_ROOT=%REPO_ROOT%"
    goto :done
)
if exist "E:\Tools\OmniParser\omnitool\omniparserserver" (
    set "OMNI_ROOT=E:\Tools\OmniParser"
    goto :done
)
if exist "%REPO_ROOT%\omnitool\omniparserserver" (
    set "OMNI_ROOT=%REPO_ROOT%"
    goto :done
)
set "OMNI_ROOT=E:\Tools\OmniParser"
:done
