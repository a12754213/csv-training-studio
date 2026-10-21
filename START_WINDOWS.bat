@echo off
setlocal
cd /d "%~dp0"
where pwsh.exe >nul 2>nul
if errorlevel 1 (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
) else (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
)
set "studio_exit=%errorlevel%"
if not "%studio_exit%"=="0" (
    echo.
    echo Startup failed. Please copy the error above for troubleshooting.
    pause
)
exit /b %studio_exit%
