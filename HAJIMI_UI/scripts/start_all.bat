@echo off
setlocal EnableExtensions
cd /d %~dp0..

echo [HAJIMI] start_all - delegating to release fullstack (L5 auto-execute)
call "%~dp0start_release_fullstack.bat"
set ERR=%ERRORLEVEL%
endlocal
exit /b %ERR%
