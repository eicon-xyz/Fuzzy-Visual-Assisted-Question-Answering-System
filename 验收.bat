@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\verify_all.bat" (
    echo [ERROR] 缺少 HAJIMI_UI\scripts\verify_all.bat
    pause
    exit /b 1
)

echo ============================================================
echo  HAJIMI 全栈验收 — 需先运行 启动全栈.bat
echo ============================================================
echo.

cd HAJIMI_UI
call scripts\verify_all.bat --require-a
set ERR=%ERRORLEVEL%
cd ..

echo.
if %ERR% EQU 0 (
    echo [OK] 验收通过 — L4 + L5 端点就绪
) else (
    echo [FAIL] 验收未通过 — 确认 8010 / 8011 已启动且 server\.env 已配置 LLM_API_KEY
)
pause
endlocal
exit /b %ERR%
