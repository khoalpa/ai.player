$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "download_whisper_model.ps1")
& (Join-Path $PSScriptRoot "download_translator_models.ps1")
& (Join-Path $PSScriptRoot "download_tessdata_models.ps1")

Write-Host "Core offline model download steps completed. VieNeu-TTS model download still depends on the selected release/source."
