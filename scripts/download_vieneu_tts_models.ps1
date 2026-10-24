param([string]$Python = "", [switch]$Cuda)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
& (Join-Path $PSScriptRoot "setup_vieneu_runtime.ps1") -Python $Python -Cuda:$Cuda
if ($LASTEXITCODE -ne 0) { throw "VieNeu runtime setup failed." }
$RuntimePython = Join-Path $ProjectRoot ".venv-vieneu\Scripts\python.exe"
$DownloadArgs = @("-X", "utf8", (Join-Path $PSScriptRoot "download_vieneu_v3.py"))
if ($Cuda) { $DownloadArgs += "--cuda" }
& $RuntimePython @DownloadArgs
if ($LASTEXITCODE -ne 0) { throw "VieNeu v3 model download failed." }
