$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Target = Join-Path $ProjectRoot "models\ocr\tessdata"
New-Item -ItemType Directory -Force -Path $Target | Out-Null

$Languages = @("eng", "vie", "osd")
foreach ($lang in $Languages) {
    $url = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lang.traineddata"
    $out = Join-Path $Target "$lang.traineddata"
    if (Test-Path $out) {
        Write-Host "Already exists: $out"
        continue
    }
    Write-Host "Downloading $lang..."
    Invoke-WebRequest -Uri $url -OutFile $out
}

Write-Host "Tessdata ready: $Target"
