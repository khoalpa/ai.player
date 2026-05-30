param(
    [string]$Python = "",
    [string]$Package = $(if ($env:AI_PLAYER_TELEGRAM_CLIENT_PACKAGE) { $env:AI_PLAYER_TELEGRAM_CLIENT_PACKAGE } elseif ($env:AI_PLAYER_PRIVATE_TELEGRAM_PACKAGE) { $env:AI_PLAYER_PRIVATE_TELEGRAM_PACKAGE } else { "ai-player-telegram-client" })
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

Write-Host "Installing Telegram client plugin: $Package"
& $Python -m pip install --upgrade $Package
& $Python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('ai_player_telegram_client.adapter') else 1)"
Write-Host "Telegram client plugin ready."
