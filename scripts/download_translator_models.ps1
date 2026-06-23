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

$CTranslate2Converter = Join-Path $ProjectRoot ".venv\Scripts\ct2-transformers-converter.exe"
if (-not (Test-Path $CTranslate2Converter)) {
    $CTranslate2Converter = "ct2-transformers-converter"
}
$Ct2Target = Join-Path $ProjectRoot "models\translation\nllb-200-distilled-600M-ct2-int8"
& $CTranslate2Converter --model $Target --output_dir $Ct2Target --quantization int8 --force
Write-Host "Translation CTranslate2 int8 model ready: $Ct2Target"
