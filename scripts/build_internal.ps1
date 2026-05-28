param(
    [string]$Python = "",
    [string]$PrivateYtdlpPluginPackage = $env:AI_PLAYER_PRIVATE_YTDLP_PLUGIN_PACKAGE,
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

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

if ($PrivateYtdlpPluginPackage) {
    & $Python -m pip install $PrivateYtdlpPluginPackage
}

if (-not $ExtraYtdlpHosts) {
    throw "Pass -ExtraYtdlpHosts or set AI_PLAYER_EXTRA_YTDLP_HOSTS for the internal plugin hosts."
}

$PreviousInclude = $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS
$PreviousHosts = $env:AI_PLAYER_EXTRA_YTDLP_HOSTS

try {
    $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS = "1"
    $env:AI_PLAYER_EXTRA_YTDLP_HOSTS = $ExtraYtdlpHosts

    & $BuildPortable `
        -Python $Python `
        -InstallDependencies:$InstallDependencies `
        -CodeSigningCertThumbprint $CodeSigningCertThumbprint `
        -CodeSigningPfxPath $CodeSigningPfxPath `
        -CodeSigningPfxPassword $CodeSigningPfxPassword `
        -TimestampServer $TimestampServer `
        -RequireSignature:$RequireSignature `
        -ListCodeSigningCerts:$ListCodeSigningCerts
} finally {
    $env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS = $PreviousInclude
    $env:AI_PLAYER_EXTRA_YTDLP_HOSTS = $PreviousHosts
}
