@echo off
setlocal
cd /d "%~dp0"

set "AIRPOINT_EXE=%~dp0dist\AirPoint\AirPoint.exe"
if exist "%AIRPOINT_EXE%" (
    start "" /min "%AIRPOINT_EXE%" --minimized
    exit /b 0
)

start "" /min powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Minimized
exit /b 0
