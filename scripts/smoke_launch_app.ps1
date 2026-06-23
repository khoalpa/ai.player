[CmdletBinding()]
param(
    [string]$AppPath = "",
    [string[]]$ArgumentList = @(),
    [switch]$Source,
    [int]$Seconds = 8,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Source) {
    if (-not $AppPath) {
        $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $VenvPython) {
            $AppPath = $VenvPython
        } else {
            $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
            if ($PythonCommand) {
                $AppPath = $PythonCommand.Source
            }
        }
    }
    if ($ArgumentList.Count -eq 0) {
        $ArgumentList = @("main.py")
    } elseif ($ArgumentList[0] -ne "main.py") {
        $ArgumentList = @("main.py") + $ArgumentList
    }
}

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
    throw "No app executable found. Pass -AppPath, use -Source, or build with PyInstaller first."
}

$ResolvedAppPath = if (Test-Path -LiteralPath $AppPath) {
    (Resolve-Path -LiteralPath $AppPath).Path
} else {
    $Command = Get-Command $AppPath -ErrorAction SilentlyContinue
    if (-not $Command) {
        throw "App executable not found: $AppPath"
    }
    $Command.Source
}
if ($Seconds -lt 1) {
    throw "-Seconds must be at least 1."
}

$StartProcessArgs = @{
    FilePath = $ResolvedAppPath
    PassThru = $true
    WindowStyle = "Hidden"
    WorkingDirectory = $ProjectRoot
}
if ($ArgumentList.Count -gt 0) {
    $StartProcessArgs.ArgumentList = $ArgumentList
}

$Process = Start-Process @StartProcessArgs
try {
    Start-Sleep -Seconds $Seconds
    if ($Process.HasExited) {
        throw "Launch smoke failed: $ResolvedAppPath exited within $Seconds seconds with code $($Process.ExitCode)."
    }
    $ArgumentSummary = if ($ArgumentList.Count -gt 0) { " $($ArgumentList -join ' ')" } else { "" }
    Write-Output "Launch smoke passed: $ResolvedAppPath$ArgumentSummary stayed running for $Seconds seconds."
} finally {
    if (-not $KeepRunning -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit(5000) | Out-Null
    }
}
