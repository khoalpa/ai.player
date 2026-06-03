param(
    [string]$Python = "",
    [string]$Package = $(if ($env:AI_PLAYER_TELEGRAM_CLIENT_PACKAGE) { $env:AI_PLAYER_TELEGRAM_CLIENT_PACKAGE } elseif ($env:AI_PLAYER_PRIVATE_TELEGRAM_PACKAGE) { $env:AI_PLAYER_PRIVATE_TELEGRAM_PACKAGE } else { "" })
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalPackage = Join-Path $ProjectRoot "plugins\ai-player-telegram-client"
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}
if (-not $Package) {
    $Package = if (Test-Path $LocalPackage) { $LocalPackage } else { "ai-player-telegram-client" }
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

Write-Host "Installing Telegram client plugin: $Package"
Invoke-NativeCommand $Python -m pip install --upgrade $Package
Invoke-NativeCommand $Python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('ai_player_telegram_client.adapter') else 1)"
Write-Host "Telegram client plugin ready."
