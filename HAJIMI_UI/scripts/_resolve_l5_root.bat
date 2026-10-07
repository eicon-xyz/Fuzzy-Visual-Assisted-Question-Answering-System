@echo off
setlocal EnableExtensions
:: Sets L5_ROOT in caller scope. Call from scripts\ with %~dp0

if defined HAJIMI_L5_ROOT (
    set "L5_ROOT=%HAJIMI_L5_ROOT%"
    endlocal & set "L5_ROOT=%L5_ROOT%"
    exit /b 0
)

set "L5_FLAT=%~dp0..\..\server_A"
set "L5_NESTED=%~dp0..\..\server_A\server_A"
set "L5_LEGACY=%~dp0..\..\new_JIMI\HAJIMI_UI"

if exist "%L5_FLAT%\scripts\start_server.bat" (
    set "L5_ROOT=%L5_FLAT%"
) else if exist "%L5_NESTED%\scripts\start_server.bat" (
    set "L5_ROOT=%L5_NESTED%"
) else if exist "%L5_LEGACY%\scripts\start_server.bat" (
    echo [HAJIMI] WARN: Using deprecated new_JIMI\HAJIMI_UI ¡ª prefer server_A
    set "L5_ROOT=%L5_LEGACY%"
) else (
    set "L5_ROOT=%L5_FLAT%"
)

endlocal & set "L5_ROOT=%L5_ROOT%"
exit /b 0
