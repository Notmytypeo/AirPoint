param(
    [switch]$Minimized
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    py -m venv $Venv
}

& $Python -c "import mediapipe, cv2, PySide6, numpy, uiautomation" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing AirPoint dependencies..." -ForegroundColor Cyan
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed. Check the messages above and try again."
    }
}

$Main = Join-Path $Root "main.py"
if ($Minimized) {
    & $Python $Main --minimized
} else {
    & $Python $Main
}
exit $LASTEXITCODE
