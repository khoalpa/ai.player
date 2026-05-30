param(
    [string]$AppPath = "",
    [int]$Seconds = 8,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $AppPath) {
    $Candidates = @(
        (Join-Path $ProjectRoot "data\tmp\ci-dist\AI Player\AI Player.exe"),
        (Join-Path $ProjectRoot "dist\portable\AI Player Lite\AI Player\AI Player.exe"),
        (Join-Path $ProjectRoot "dist\AI Player\AI Player.exe")
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate) {
            $AppPath = $Candidate
            break
        }
    }
}

if (-not $AppPath) {
    throw "No app executable found. Pass -AppPath or build with PyInstaller first."
}

$ResolvedAppPath = (Resolve-Path -LiteralPath $AppPath).Path
if ($Seconds -lt 1) {
    throw "-Seconds must be at least 1."
}

$Process = Start-Process -FilePath $ResolvedAppPath -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds $Seconds
    if ($Process.HasExited) {
        throw "Launch smoke failed: $ResolvedAppPath exited within $Seconds seconds with code $($Process.ExitCode)."
    }
    Write-Output "Launch smoke passed: $ResolvedAppPath stayed running for $Seconds seconds."
} finally {
    if (-not $KeepRunning -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit(5000) | Out-Null
    }
}
