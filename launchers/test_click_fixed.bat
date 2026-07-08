@echo off
cd /d %~dp0..\HAJIMI_UI\scripts\dev
call test_click_fixed.bat
exit /b %ERRORLEVEL%
