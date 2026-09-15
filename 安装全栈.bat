@echo off
setlocal EnableExtensions
cd /d %~dp0

echo ============================================================
echo  HAJIMI 安装 - 仅 L5 自动执行模式
echo  创建 2 个环境: B 端 UI + L5 Sidecar(8011)
echo  L5 环境含 torch，首次约 10-30 分钟
echo ============================================================

if not exist "HAJIMI_UI\main.py" (
    echo [ERROR] 请在仓库根目录运行 - 未找到 HAJIMI_UI\
    pause
    exit /b 1
)
if not exist "server_A\scripts\start_server.bat" (
    echo [ERROR] 缺少 server_A\ - L5 自动执行无法工作
    echo   请确保目录结构:
    echo     repo\HAJIMI_UI\
    echo     repo\server_A\
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 python - 请先安装 Python 3.12+
    pause
    exit /b 1
)

cd HAJIMI_UI

echo.
echo [1/3] B 端 UI 环境 ...
call scripts\ensure_ui_env.bat
if errorlevel 1 goto fail

echo.
echo [2/3] L5 Sidecar :8011 环境 - 含 torch 可能 10-30 分钟 ...
call scripts\ensure_l5_sidecar_env.bat
if errorlevel 1 goto fail

echo.
echo [3/3] 初始化 Sidecar .env 与 L5 设置 ...
call "%~dp0HAJIMI_UI\scripts\_resolve_l5_root.bat"
set "PYTHON=python"
if exist "%L5_ROOT%\server\.venv\Scripts\python.exe" set "PYTHON=%L5_ROOT%\server\.venv\Scripts\python.exe"
"%PYTHON%" scripts\bootstrap_release_env.py
if errorlevel 1 goto fail
"%PYTHON%" scripts\apply_l5_settings.py
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  安装完成。下一步:
echo    1. 编辑 server_A\server\.env 填入 DEEPSEEK_API_KEY
echo    2. 双击运行 启动全栈.bat
echo       即 HAJIMI_UI\scripts\start_release_fullstack.bat
echo ============================================================
pause
cd ..
exit /b 0

:fail
echo.
echo [ERROR] 安装失败 - 见上方报错。
pause
cd ..
exit /b 1
