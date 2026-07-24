param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$InstallerSpec = Join-Path $Root "installer.iss"

if (-not (Test-Path -LiteralPath $Python)) {
    throw ".venv not found. Run '.\run.ps1' once before building the installer."
}

$Version = (& $Python -c "from app import __version__; print(__version__)").Trim()
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "app.__version__ must use MAJOR.MINOR.PATCH format. Found: $Version"
}

if (-not $SkipAppBuild) {
    & (Join-Path $Root "build_exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "AirPoint application build failed."
    }
}

$ISCCCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$ISCCPath = if ($null -ne $ISCCCommand) { $ISCCCommand.Source } else { $null }
if ([string]::IsNullOrWhiteSpace($ISCCPath)) {
    foreach ($Base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ([string]::IsNullOrWhiteSpace($Base)) {
            continue
        }
        $Candidate = Join-Path $Base "Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $Candidate) {
            $ISCCPath = $Candidate
            break
        }
    }
}
if ([string]::IsNullOrWhiteSpace($ISCCPath)) {
    throw "Inno Setup 6 was not found. Install it, then rerun this script."
}

& $ISCCPath "/DMyAppVersion=$Version" $InstallerSpec
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$Installer = Join-Path $Root "installer_output\AirPoint_Setup_$Version.exe"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "Expected installer was not created: $Installer"
}

Write-Host "AirPoint $Version installer created:" -ForegroundColor Green
Write-Host $Installer
