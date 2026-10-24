[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Manifest = Join-Path $ProjectRoot "models\tts\vieneu\v3-turbo\manifest.json"
$Report = Join-Path $ProjectRoot "output\vieneu-v3-verification\cpu-report.json"
if (-not (Test-Path -LiteralPath $Manifest) -or -not (Test-Path -LiteralPath $Report)) {
    throw "Download v3 Turbo and run scripts/verify_vieneu_offline.py before cleanup."
}
$Bundle = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$Verification = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ($Bundle.sdk_version -ne "3.8.3" -or $Verification.sdk_version -ne "3.8.3" -or
    -not $Verification.model_hashes_verified -or $Verification.network -notlike "*zero network attempts*") {
    throw "A verified, fully offline v3 Turbo bundle is required."
}
# Only these obsolete AI Player-owned paths may be removed. Do not touch shared HF caches or exports.
$LegacyPaths = @(
    "ai_player\vieneu_tts",
    "models\tts\vieneu\standard",
    "models\tts\vieneu\turbo",
    "models\tts\vieneu\codecs",
    "models\tts\vieneu\decoders",
    "models\tts\vieneu\_hf-cache"
)
foreach ($RelativePath in $LegacyPaths) {
    $Target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath))
    if (-not $Target.StartsWith($ProjectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Cleanup target is outside this project: $Target"
    }
    if (-not (Test-Path -LiteralPath $Target)) { continue }
    if ((Get-Item -LiteralPath $Target).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to remove a linked directory: $Target"
    }
    if ($PSCmdlet.ShouldProcess($Target, "Permanently remove obsolete VieNeu files")) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}
