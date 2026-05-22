param(
    [string]$Python = "",
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistRoot = Join-Path $ProjectRoot "dist"
$PortableRoot = Join-Path $DistRoot "portable\AI Player Lite"

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

if ($InstallDependencies) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e "$ProjectRoot[packaging,audio-separation]"
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: .\scripts\build_portable.ps1 -InstallDependencies"
}

if (Test-Path $PortableRoot) {
    Remove-Item -LiteralPath $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    "$ProjectRoot\AI Player.spec"

$AppDist = Join-Path $DistRoot "AI Player"
if (-not (Test-Path $AppDist)) {
    throw "PyInstaller did not create expected app folder: $AppDist"
}

Copy-Item -LiteralPath $AppDist -Destination $PortableRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $PortableRoot -Force
if (Test-Path (Join-Path $ProjectRoot "samples")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "samples") -Destination $PortableRoot -Recurse -Force
}

$launcher = Join-Path $PortableRoot "Run AI Player.bat"
@'
@echo off
set "APP_ROOT=%~dp0"
if exist "%APP_ROOT%tools\ffmpeg\bin" set "PATH=%APP_ROOT%tools\ffmpeg\bin;%PATH%"
if exist "%APP_ROOT%tools\ffmpeg" set "PATH=%APP_ROOT%tools\ffmpeg;%PATH%"
start "" "%APP_ROOT%AI Player\AI Player.exe"
'@ | Set-Content -LiteralPath $launcher -Encoding ASCII

Write-Output "Portable Lite ready: $PortableRoot"
