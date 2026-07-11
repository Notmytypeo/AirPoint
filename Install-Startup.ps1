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

$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$RunScript = Join-Path $Root "run.ps1"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShell
$Shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$RunScript`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 3
$Shortcut.Description = "Start AirPoint gesture control full-screen at Windows sign-in"
$Shortcut.Save()

Write-Host "AirPoint will now start full-screen after you sign in to Windows." -ForegroundColor Green
Write-Host "Startup shortcut: $ShortcutPath"
