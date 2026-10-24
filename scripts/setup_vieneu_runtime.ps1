param([string]$Python = "", [switch]$Cuda)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
}
$Runtime = Join-Path $ProjectRoot ".venv-vieneu"
$RuntimePython = Join-Path $Runtime "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $RuntimePython)) {
    & $Python -m venv $Runtime
    if ($LASTEXITCODE -ne 0) { throw "Could not create VieNeu runtime." }
}
& $RuntimePython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements-vieneu.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install VieNeu v3 Turbo." }
if ($Cuda) {
    & $RuntimePython -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { throw "Could not install VieNeu CUDA runtime." }
    & $RuntimePython -m pip install transformers==4.57.6 safetensors
    if ($LASTEXITCODE -ne 0) { throw "Could not install VieNeu GPU dependencies." }
}
& $RuntimePython -X utf8 (Join-Path $PSScriptRoot "prepare_vieneu_runtime.py")
if ($LASTEXITCODE -ne 0) { throw "Could not prepare the v3-only runtime." }
& $RuntimePython -m pip check
if ($LASTEXITCODE -ne 0) { throw "VieNeu runtime dependencies conflict." }
Write-Output "VieNeu v3 Turbo runtime ready: $RuntimePython"
