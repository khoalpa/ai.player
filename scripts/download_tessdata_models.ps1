param(
    [ValidateSet("fast", "best")]
    [string]$Quality = "fast",
    [string[]]$Languages = @("eng", "vie", "osd")
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Repo = if ($Quality -eq "best") { "tessdata_best" } else { "tessdata_fast" }
$Folder = if ($Quality -eq "best") { "tessdata_best" } else { "tessdata" }
$Target = Join-Path $ProjectRoot "models\ocr\$Folder"
New-Item -ItemType Directory -Force -Path $Target | Out-Null

foreach ($lang in $Languages) {
    $url = "https://github.com/tesseract-ocr/$Repo/raw/main/$lang.traineddata"
    $out = Join-Path $Target "$lang.traineddata"
    if (Test-Path $out) {
        Write-Host "Already exists: $out"
        continue
    }
    Write-Host "Downloading $lang..."
    Invoke-WebRequest -Uri $url -OutFile $out
}

Write-Host "Tessdata $Quality ready: $Target"
