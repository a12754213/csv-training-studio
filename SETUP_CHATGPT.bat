@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_chatgpt.ps1"
if errorlevel 1 (
  echo Setup failed. Copy the error above.
  pause
  exit /b 1
)
pause
