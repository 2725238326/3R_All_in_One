<#
.SYNOPSIS
    Build the 3R All-in-One backend as a standalone executable using PyInstaller.

.DESCRIPTION
    This script builds the FastAPI backend into a single .exe file that can be
    embedded as a Tauri sidecar. The output is placed in dist/3r-backend.exe.

.EXAMPLE
    .\tools\build_backend.ps1

.NOTES
    Requires: Python 3.11+, PyInstaller, project dependencies installed
#>

param(
    [switch]$Clean,
    [switch]$NoCopy
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== 3R Backend Build ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

# Activate virtual environment if exists
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    . $VenvActivate
}

# Clean previous build artifacts
if ($Clean) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    $BuildDir = Join-Path $ProjectRoot "build"
    $DistDir = Join-Path $ProjectRoot "dist"
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
}

# Check PyInstaller
Write-Host "Checking PyInstaller..." -ForegroundColor Yellow
try {
    $null = python -c "import PyInstaller" 2>&1
} catch {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Run PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Yellow
$SpecFile = Join-Path $ProjectRoot "tools\3r_backend.spec"

Push-Location $ProjectRoot
try {
    pyinstaller --clean --noconfirm $SpecFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

# Verify output
$ExePath = Join-Path $ProjectRoot "dist\3r-backend.exe"
if (-not (Test-Path $ExePath)) {
    throw "Build failed: $ExePath not found"
}

$ExeSize = (Get-Item $ExePath).Length / 1MB
Write-Host "Build successful: $ExePath ($([math]::Round($ExeSize, 2)) MB)" -ForegroundColor Green

# Copy to Tauri binaries folder
if (-not $NoCopy) {
    $TauriBinDir = Join-Path $ProjectRoot "client\src-tauri\binaries"
    if (-not (Test-Path $TauriBinDir)) {
        New-Item -ItemType Directory -Path $TauriBinDir -Force | Out-Null
    }
    
    # Tauri requires target triple suffix for sidecar
    $TargetExe = Join-Path $TauriBinDir "3r-backend-x86_64-pc-windows-msvc.exe"
    Copy-Item -Force $ExePath $TargetExe
    Write-Host "Copied to: $TargetExe" -ForegroundColor Green
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
