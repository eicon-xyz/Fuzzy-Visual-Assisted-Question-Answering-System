@echo off
setlocal EnableExtensions
cd /d %~dp0

echo ============================================================
echo  HAJIMI L4+L5 全栈安装（方案一：源码交付包）
echo  将配置 B 端 + A 端(8010) + L5 Sidecar(8011) 三个 venv
echo ============================================================

if not exist "HAJIMI_UI\main.py" (
    echo [ERROR] 请在仓库根目录运行（需含 HAJIMI_UI\）
    goto fail
)
if not exist "server_A\scripts\start_server.bat" (
    echo [ERROR] 缺少 server_A\ — L5 自动执行无法工作
    echo   请确保目录结构:
    echo     repo\HAJIMI_UI\
    echo     repo\server_A\
    goto fail
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 python — 请先安装 Python 3.12+
    goto fail
)

cd HAJIMI_UI

echo.
echo [1/4] B 端 UI 环境 ...
call scripts\ensure_ui_env.bat
if errorlevel 1 goto fail

echo.
echo [2/4] A 端 :8010 环境 ...
call scripts\ensure_server_env.bat
if errorlevel 1 goto fail

echo.
echo [3/4] L5 Sidecar :8011 环境 ^(含 torch，可能 10-30 分钟^) ...
call scripts\ensure_l5_sidecar_env.bat
if errorlevel 1 goto fail

echo.
echo [4/4] 初始化 .env 并同步 8010 -^> 8011 ...
if exist server\.venv\Scripts\python.exe (
    set PYTHON=server\.venv\Scripts\python.exe
) else (
    set PYTHON=python
)
"%PYTHON%" scripts\bootstrap_release_env.py
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  安装完成
echo  下一步:
echo    1. 编辑 HAJIMI_UI\server\.env  填入 LLM_API_KEY ^(Vision 模型^)
echo    2. 双击 启动全栈.bat
echo    3. 验收: 验收.bat
echo ============================================================
cd ..
endlocal
exit /b 0

:fail
echo.
echo [ERROR] 安装失败 — 见上方提示
cd /d %~dp0
pause
endlocal
exit /b 1
