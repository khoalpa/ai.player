param(
    [string]$Python = "",
    [string]$Package = $(if ($env:AI_PLAYER_ADULT_EXTRACTORS_PACKAGE) { $env:AI_PLAYER_ADULT_EXTRACTORS_PACKAGE } elseif ($env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE) { $env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE } else { "ai-player-adult-extractors" })
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

Write-Host "Installing yt-dlp adult extractor plugin: $Package"
& $Python -m pip install --upgrade $Package
& $Python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('yt_dlp_plugins.extractor.adult_sites') else 1)"
Write-Host "Adult extractors plugin ready."
