param(
    [string]$Python = "",
    [string]$PrivateYtdlpPluginPackage = $env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE,
    [string]$PrivateTelegramPackage = $env:AI_PLAYER_PRIVATE_TELEGRAM_PACKAGE,
    [string]$ExtraYtdlpHosts = $env:AI_PLAYER_EXTRA_YTDLP_HOSTS,
    [switch]$InstallDependencies,
    [string]$CodeSigningCertThumbprint = "",
    [string]$CodeSigningPfxPath = "",
    [securestring]$CodeSigningPfxPassword,
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$RequireSignature,
    [switch]$ListCodeSigningCerts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildPortable = Join-Path $PSScriptRoot "build_portable.ps1"
$PortableLauncher = Join-Path $ProjectRoot "dist\portable\AI Player Lite\Run AI Player.bat"

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

if ($PrivateYtdlpPluginPackage) {
    & $Python -m pip install $PrivateYtdlpPluginPackage
}

if ($PrivateTelegramPackage) {
    & $Python -m pip install $PrivateTelegramPackage
}

if ($PrivateYtdlpPluginPackage -and -not $ExtraYtdlpHosts) {
    throw "Pass -ExtraYtdlpHosts or set AI_PLAYER_EXTRA_YTDLP_HOSTS for the internal plugin hosts."
}

$PreviousInclude = $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS
$PreviousTelegramInclude = $env:AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN
$PreviousHosts = $env:AI_PLAYER_EXTRA_YTDLP_HOSTS

try {
    if ($PrivateYtdlpPluginPackage -or $ExtraYtdlpHosts) {
        $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS = "1"
    }
    if ($PrivateTelegramPackage) {
        $env:AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN = "1"
    }
    if ($ExtraYtdlpHosts) {
        $env:AI_PLAYER_EXTRA_YTDLP_HOSTS = $ExtraYtdlpHosts
    }

    & $BuildPortable `
        -Python $Python `
        -InstallDependencies:$InstallDependencies `
        -CodeSigningCertThumbprint $CodeSigningCertThumbprint `
        -CodeSigningPfxPath $CodeSigningPfxPath `
        -CodeSigningPfxPassword $CodeSigningPfxPassword `
        -TimestampServer $TimestampServer `
        -RequireSignature:$RequireSignature `
        -ListCodeSigningCerts:$ListCodeSigningCerts

    if ($ExtraYtdlpHosts -and (Test-Path $PortableLauncher)) {
        $EscapedHosts = $ExtraYtdlpHosts.Replace("%", "%%")
        $LauncherContent = Get-Content -LiteralPath $PortableLauncher -Raw
        if ($LauncherContent -match '(?m)^set "AI_PLAYER_EXTRA_YTDLP_HOSTS=.*"$') {
            $LauncherContent = $LauncherContent -replace '(?m)^set "AI_PLAYER_EXTRA_YTDLP_HOSTS=.*"$', "set `"AI_PLAYER_EXTRA_YTDLP_HOSTS=$EscapedHosts`""
            Set-Content -LiteralPath $PortableLauncher -Value $LauncherContent -Encoding ASCII
        } else {
            $LauncherContent = $LauncherContent -replace 'start ""', "set `"AI_PLAYER_EXTRA_YTDLP_HOSTS=$EscapedHosts`"`r`nstart `"`""
            Set-Content -LiteralPath $PortableLauncher -Value $LauncherContent -Encoding ASCII
        }
    }
} finally {
    $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS = $PreviousInclude
    $env:AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN = $PreviousTelegramInclude
    $env:AI_PLAYER_EXTRA_YTDLP_HOSTS = $PreviousHosts
}
