@echo off
setlocal
cd /d "%~dp0"

set "AIRPOINT_EXE=%~dp0dist\AirPoint\AirPoint.exe"
if exist "%AIRPOINT_EXE%" (
    start "" "%AIRPOINT_EXE%"
    exit /b 0
)

start "" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0run.ps1"
exit /b 0
