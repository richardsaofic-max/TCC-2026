@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" iniciar.py
  goto done
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" iniciar.py
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 iniciar.py
) else (
  python iniciar.py
)
:done
pause
