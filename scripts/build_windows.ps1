# Build LyPy.exe on Windows (icons, asset preflight, PyInstaller).
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Require-File([string]$Path, [string]$Hint) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required file: $Path`n$Hint"
    }
}

function Require-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) {
        throw "Python launcher 'py' not found. Install Python 3.10+ from https://www.python.org/downloads/"
    }
}

Require-Python

Write-Host "== LyPy Windows build ==" -ForegroundColor Cyan
Write-Host "Repository root: $Root"

Write-Host "`n[1/4] Generating UI assets..." -ForegroundColor Yellow
Push-Location (Join-Path $Root "LyPy")
try {
    & py -3 generate_icons.py
    if ($LASTEXITCODE -ne 0) {
        throw "generate_icons.py failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$assetDir = Join-Path $Root "LyPy\assets"
$fontBold = Join-Path $assetDir "fonts\NunitoSans-Bold.ttf"
$fontLegacy = Join-Path $assetDir "fonts\Nunito-Variable.ttf"

Write-Host "`n[2/4] Verifying bundled assets..." -ForegroundColor Yellow
if (-not (Test-Path $fontBold) -and -not (Test-Path $fontLegacy)) {
    Write-Host "Downloading Nunito Sans font pack..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "LyPy")
    try {
        py -3 -c "from font_pack import ensure_font_pack; ensure_font_pack(force=True)"
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path $fontBold) -and -not (Test-Path $fontLegacy)) {
    throw "Missing lyrics font under LyPy\assets\fonts\ (run LyPy once online)."
}

$requiredIcons = @(
    "app_icon.png",
    "btn_play.png",
    "btn_pause.png",
    "btn_prev.png",
    "btn_next.png",
    "btn_settings.png"
)
foreach ($name in $requiredIcons) {
    Require-File (Join-Path $assetDir $name) "Re-run: cd LyPy; py -3 generate_icons.py"
}

$scriptsDir = Join-Path $Root "scripts"
if (-not (Test-Path -LiteralPath $scriptsDir)) {
    New-Item -ItemType Directory -Path $scriptsDir | Out-Null
}

Write-Host "`n[3/4] Checking build dependencies..." -ForegroundColor Yellow
& py -3 -m pip show pyinstaller 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing requirements-dev.txt ..."
    & py -3 -m pip install -r (Join-Path $Root "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "pip install -r requirements-dev.txt failed"
    }
}

& py -3 -m pip show PyQt5 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing runtime requirements for PyInstaller analysis ..."
    & py -3 -m pip install -r (Join-Path $Root "LyPy\requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "pip install -r LyPy/requirements.txt failed"
    }
}

$running = Get-Process -Name "LyPy" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Stopping running LyPy.exe before rebuild..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Seconds 1
}

Write-Host "`n[4/4] Running PyInstaller via build_exe.py ..." -ForegroundColor Yellow
& py -3 (Join-Path $Root "build_exe.py")
if ($LASTEXITCODE -ne 0) {
    throw "build_exe.py failed with exit code $LASTEXITCODE"
}

$exe = Join-Path $Root "dist\LyPy.exe"
Require-File $exe "PyInstaller did not produce dist\LyPy.exe"

$sizeMb = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
Write-Host "`nSuccess: $exe ($sizeMb MB)" -ForegroundColor Green
Write-Host "Do not commit LyPy.spec (machine paths). It is listed in .gitignore."
