@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_lstm.ps1"
if errorlevel 1 (
  echo LSTM setup failed. Copy the error above.
  pause
  exit /b 1
)
pause
