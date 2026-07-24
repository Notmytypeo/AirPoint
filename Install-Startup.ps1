param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "AirPoint.lnk"

if ($Remove) {
    Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue
    Write-Host "AirPoint was removed from Windows startup." -ForegroundColor Yellow
    exit 0
}

$PackagedExe = Join-Path $Root "dist\AirPoint\AirPoint.exe"
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$RunScript = Join-Path $Root "run.ps1"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
if (Test-Path -LiteralPath $PackagedExe) {
    $Shortcut.TargetPath = $PackagedExe
    $Shortcut.Arguments = "--minimized"
} else {
    $Shortcut.TargetPath = $PowerShell
    $Shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$RunScript`" -Minimized"
}
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Start AirPoint gesture control in the background at Windows sign-in"
$Shortcut.Save()

Write-Host "AirPoint will now start in the background after you sign in to Windows." -ForegroundColor Green
Write-Host "Startup shortcut: $ShortcutPath"
