# ==============================================================================
# Build AirPoint standalone .exe using PyInstaller
# ==============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$Spec = Join-Path $Root "AirPoint.spec"

if (-not (Test-Path $Python)) {
    Write-Error ".venv not found. Run '.\run.ps1' once first to create the virtual environment."
    exit 1
}

if (-not (Test-Path $Spec)) {
    Write-Error "AirPoint.spec is missing. Restore the tracked build specification before building."
    exit 1
}

$Version = (& $Python -c "from app import __version__; print(__version__)").Trim()
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
    Write-Error "app.__version__ must use MAJOR.MINOR.PATCH format. Found: $Version"
    exit 1
}
$Major = [int]$Matches[1]
$Minor = [int]$Matches[2]
$Patch = [int]$Matches[3]
$VersionFile = Join-Path ([System.IO.Path]::GetTempPath()) "AirPoint-version-info.txt"
$VersionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($Major, $Minor, $Patch, 0),
    prodvers=($Major, $Minor, $Patch, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'AirPoint'),
          StringStruct(u'FileDescription', u'AirPoint Gesture Control'),
          StringStruct(u'FileVersion', u'$Version'),
          StringStruct(u'InternalName', u'AirPoint'),
          StringStruct(u'OriginalFilename', u'AirPoint.exe'),
          StringStruct(u'ProductName', u'AirPoint'),
          StringStruct(u'ProductVersion', u'$Version')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($VersionFile, $VersionInfo, $Utf8NoBom)
$env:AIRPOINT_VERSION_FILE = $VersionFile

# Install PyInstaller if not present. Checking with find_spec avoids a missing
# module traceback becoming a terminating native-command error in PowerShell.
& $Python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('PyInstaller') else 1)"
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
Write-Host "   Version $Version                                 " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Run PyInstaller with the spec file
& $Python -m PyInstaller --clean --noconfirm $Spec

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed! ❌"
    exit 1
}

Write-Host "--------------------------------------------------" -ForegroundColor Yellow
Write-Host "Build completed successfully! ✅" -ForegroundColor Green
Write-Host "Output: dist\AirPoint\" -ForegroundColor White
Write-Host ""
Write-Host "To test, run: dist\AirPoint\AirPoint.exe" -ForegroundColor White
