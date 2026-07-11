# ==============================================================================
# Build AirPoint standalone .exe using PyInstaller
# ==============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

if (-not (Test-Path $Python)) {
    Write-Error ".venv not found. Run '.\run.ps1' once first to create the virtual environment."
    exit 1
}

# Install PyInstaller if not present
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
    & $Pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install PyInstaller."
        exit 1
    }
}

# Ensure the hand-landmarker model exists (needed for bundling)
if (-not (Test-Path (Join-Path $Root "models\hand_landmarker.task"))) {
    Write-Host "Downloading hand-landmarker model..." -ForegroundColor Cyan
    & $Python -c "from app.model_manager import ensure_hand_model; ensure_hand_model()"
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   Building AirPoint standalone executable...      " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Run PyInstaller with the spec file
& $Python -m PyInstaller --clean --noconfirm (Join-Path $Root "AirPoint.spec")

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed! ❌"
    exit 1
}

Write-Host "--------------------------------------------------" -ForegroundColor Yellow
Write-Host "Build completed successfully! ✅" -ForegroundColor Green
Write-Host "Output: dist\AirPoint\" -ForegroundColor White
Write-Host ""
Write-Host "To test, run: dist\AirPoint\AirPoint.exe" -ForegroundColor White
