@echo off
setlocal EnableExtensions
cd /d %~dp0

if not exist "HAJIMI_UI\scripts\verify_all.bat" (
    echo [ERROR] 缺少 HAJIMI_UI\scripts\verify_all.bat
    pause
    exit /b 1
)

echo ============================================================
echo  HAJIMI 全栈验收 - 需先运行 启动全栈.bat
echo ============================================================
echo.

cd HAJIMI_UI
call scripts\verify_all.bat --require-l5
set ERR=%ERRORLEVEL%
cd ..

echo.
if %ERR% EQU 0 (
    echo [OK] 验收通过 - L5 自动执行端点就绪
) else (
    echo [FAIL] 验收未通过 - 确认 Sidecar :8011 已启动且
    echo        server_A\server\.env 已配置 DEEPSEEK_API_KEY / LLM_API_KEY
)
pause
endlocal
exit /b %ERR%
