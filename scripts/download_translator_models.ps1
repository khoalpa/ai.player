param(
    [string]$Python = "",
    [string]$RepoId = "facebook/nllb-200-distilled-600M"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

$Target = Join-Path $ProjectRoot "models\translation\nllb-200-distilled-600M"
New-Item -ItemType Directory -Force -Path $Target | Out-Null

& $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$RepoId', local_dir=r'$Target', local_dir_use_symlinks=False)"
Write-Host "Translation model ready: $Target"
