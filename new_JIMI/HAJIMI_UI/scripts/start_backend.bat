@echo off
setlocal EnableExtensions
cd /d %~dp0..

if not defined HAJIMI_PORT set HAJIMI_PORT=8010
if not defined HAJIMI_HOST set HAJIMI_HOST=127.0.0.1

set "PYTHON=server\.venv\Scripts\python.exe"

echo ========================================
echo   HAJIMI Auto-Op Backend
echo   http://%HAJIMI_HOST%:%HAJIMI_PORT%
echo ========================================
echo.

:: Check OmniParser
echo [1/3] Checking OmniParser :9800 ...
"%PYTHON%" -c "import urllib.request,json; d=json.loads(urllib.request.urlopen('http://127.0.0.1:9800/probe/',timeout=5)); print(f'  GPU: {d.get(\"gpu\",{}).get(\"name\",\"?\")} | Ready: {d.get(\"ready\")} | VRAM: {d.get(\"gpu\",{}).get(\"vram_total_gb\",\"?\")}GB')" 2>nul || echo   WARNING: OmniParser not reachable at :9800

:: Check LLM
echo [2/3] Checking LLM ...
"%PYTHON%" -c "import sys; sys.path.insert(0,'.'); from server.services.llm.providers import call_llm; r=call_llm(user_text='say OK',system_prompt='Reply OK only.',temperature=0,max_tokens=10,timeout=15); print(f'  LLM: {\"OK\" if \"OK\" in r else \"FAIL\"}')" 2>nul || echo   WARNING: LLM check failed

:: Start server
echo [3/3] Starting A-end ...
echo.
"%PYTHON%" -m uvicorn server.main:app --host %HAJIMI_HOST% --port %HAJIMI_PORT%

endlocal
