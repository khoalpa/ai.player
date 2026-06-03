param(
    [string]$Python = "",
    [string]$Package = $(if ($env:AI_PLAYER_ADULT_EXTRACTORS_PACKAGE) { $env:AI_PLAYER_ADULT_EXTRACTORS_PACKAGE } elseif ($env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE) { $env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE } else { "" })
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalPackage = Join-Path $ProjectRoot "plugins\ai-player-adult-extractors"
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}
if (-not $Package) {
    $Package = if (Test-Path $LocalPackage) { $LocalPackage } else { "ai-player-adult-extractors" }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

Write-Host "Installing yt-dlp adult extractor plugin: $Package"
Invoke-NativeCommand $Python -m pip install --upgrade $Package
Invoke-NativeCommand $Python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('yt_dlp_plugins.extractor.adult_sites') else 1)"
Write-Host "Adult extractors plugin ready."
