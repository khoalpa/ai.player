$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& (Join-Path $PSScriptRoot "download_whisper_model.ps1")
& (Join-Path $PSScriptRoot "download_translator_models.ps1")

& (Join-Path $PSScriptRoot "download_vieneu_tts_models.ps1")
& (Join-Path $PSScriptRoot "download_tessdata_models.ps1")
& (Join-Path $PSScriptRoot "download_speaker_gender_model.ps1")

Write-Host "Offline model download steps completed."
