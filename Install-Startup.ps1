param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "AirPoint.lnk"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if ($Remove) {
    Remove-ItemProperty -LiteralPath $RunKey -Name "AirPoint" -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue
    Write-Host "AirPoint was removed from Windows startup." -ForegroundColor Yellow
    exit 0
}

$PackagedExe = Join-Path $Root "dist\AirPoint\AirPoint.exe"
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$RunScript = Join-Path $Root "run.ps1"
if (Test-Path -LiteralPath $PackagedExe) {
    $Command = "`"$PackagedExe`" --minimized"
} else {
    $Command = "`"$PowerShell`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$RunScript`" -Minimized"
}
New-Item -Path $RunKey -Force | Out-Null
New-ItemProperty -LiteralPath $RunKey -Name "AirPoint" -PropertyType String -Value $Command -Force | Out-Null
Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue

Write-Host "AirPoint will now start in the background after you sign in to Windows." -ForegroundColor Green
Write-Host "Startup command: $Command"
