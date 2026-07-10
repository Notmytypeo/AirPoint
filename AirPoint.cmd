@echo off
cd /d "%~dp0"
start "" /min powershell.exe -NoProfile -WindowStyle Minimized -ExecutionPolicy Bypass -File "%~dp0run.ps1"
exit /b
