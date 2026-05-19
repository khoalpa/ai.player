$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& (Join-Path $PSScriptRoot "download_whisper_model.ps1")
& (Join-Path $PSScriptRoot "download_translator_models.ps1")

$CTranslate2Converter = Join-Path $ProjectRoot ".venv\Scripts\ct2-transformers-converter.exe"
if (-not (Test-Path $CTranslate2Converter)) {
    $CTranslate2Converter = "ct2-transformers-converter"
}
$NllbModel = Join-Path $ProjectRoot "models\translation\nllb-200-distilled-600M"
$NllbCt2Model = Join-Path $ProjectRoot "models\translation\nllb-200-distilled-600M-ct2-int8"
& $CTranslate2Converter --model $NllbModel --output_dir $NllbCt2Model --quantization int8 --force

& (Join-Path $PSScriptRoot "download_vieneu_tts_models.ps1")
& (Join-Path $PSScriptRoot "download_tessdata_models.ps1")

Write-Host "Offline model download steps completed."
