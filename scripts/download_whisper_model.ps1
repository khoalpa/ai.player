param(
    [string]$Python = "",
    [string]$RepoId = "Systran/faster-whisper-base"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
}

$Target = Join-Path $ProjectRoot "models\asr\faster-whisper-base"
New-Item -ItemType Directory -Force -Path $Target | Out-Null

& $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$RepoId', local_dir=r'$Target', local_dir_use_symlinks=False)"
Write-Host "Whisper model ready: $Target"
