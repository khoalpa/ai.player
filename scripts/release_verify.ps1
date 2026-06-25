param(
    [string]$Python = "",
    [ValidateSet("Lite", "OfflineCpu", "Gpu")]
    [string[]]$BuildProfiles = @(),
    [switch]$InstallDependencies,
    [switch]$SkipPytest,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunRoot = Join-Path $ProjectRoot "data\tmp\release-verify\$RunStamp"
$SummaryPath = Join-Path $RunRoot "summary.json"
$Steps = New-Object System.Collections.Generic.List[object]

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
Push-Location $ProjectRoot
try {
    function Invoke-ReleaseStep {
        param(
            [string]$Name,
            [string]$FilePath,
            [string[]]$Arguments
        )

        $LogPath = Join-Path $RunRoot "$Name.log"
        Write-Output "==> $Name"
        $Started = Get-Date
        $Output = & $FilePath @Arguments 2>&1
        $ExitCode = if ($null -ne $global:LASTEXITCODE) { $global:LASTEXITCODE } else { 0 }
        $Output | Tee-Object -FilePath $LogPath
        $Finished = Get-Date
        $Step = [ordered]@{
            name = $Name
            command = (@($FilePath) + $Arguments) -join " "
            exit_code = $ExitCode
            started_at = $Started.ToString("o")
            finished_at = $Finished.ToString("o")
            log = $LogPath
        }
        $Steps.Add($Step) | Out-Null
        if ($ExitCode -ne 0) {
            throw "Release verification step failed: $Name. See $LogPath"
        }
    }

    function Invoke-DependencyInstall {
        param([string]$Profile)

        if (-not $InstallDependencies) {
            return
        }

        if ($Profile -eq "Lite") {
            Invoke-ReleaseStep "install-lite" $Python @("-m", "pip", "install", "-e", ".[dev,packaging]")
        } elseif ($Profile -eq "OfflineCpu") {
            Invoke-ReleaseStep "install-offline-cpu" $Python @(
                "-m",
                "pip",
                "install",
                "-e",
                ".[dev,packaging,offline-ai,audit]"
            )
        } elseif ($Profile -eq "Gpu") {
            Invoke-ReleaseStep "install-gpu" $Python @(
                "-m",
                "pip",
                "install",
                "-c",
                "constraints\windows-release-py310.txt",
                "-e",
                ".[dev,packaging,offline-ai,gpu,audio-separation,audit]"
            )
        }
    }

    function Invoke-PortableBuild {
        param([string]$Profile)

        Invoke-DependencyInstall $Profile
        $BuildArgs = @("-Python", $Python)
        if ($RequireSignature) {
            $BuildArgs += "-RequireSignature"
        }
        Invoke-ReleaseStep "build-$($Profile.ToLowerInvariant())" (Join-Path $ProjectRoot "scripts\build_portable.ps1") $BuildArgs
        Invoke-ReleaseStep "launch-$($Profile.ToLowerInvariant())" (Join-Path $ProjectRoot "scripts\smoke_launch_app.ps1") @(
            "-AppPath",
            "dist\portable\AI Player Lite\AI Player\AI Player.exe",
            "-Seconds",
            "8"
        )
    }

    Invoke-ReleaseStep "worktree" (Join-Path $ProjectRoot "scripts\check_release_worktree.ps1") @("-FailOnModified")
    Invoke-ReleaseStep "ruff" $Python @("-m", "ruff", "check", ".")
    if (-not $SkipPytest) {
        Invoke-ReleaseStep "pytest" $Python @("-m", "pytest", "-q")
    }
    Invoke-ReleaseStep "pip-check" $Python @("-m", "pip", "check")
    Invoke-ReleaseStep "runtime-doctor" $Python @(".\scripts\runtime_doctor.py", "--ci")
    Invoke-ReleaseStep "workflow-smoke" $Python @(
        ".\scripts\workflow_smoke_check.py",
        "--output",
        (Join-Path $RunRoot "workflow-smoke-current.json")
    )
    Invoke-ReleaseStep "release-smoke" $Python @("-m", "pytest", "tests\test_release_smoke.py", "-q")

    $BuildOrder = @("Lite", "OfflineCpu", "Gpu")
    $SelectedBuilds = @($BuildOrder | Where-Object { $BuildProfiles -contains $_ })
    foreach ($Profile in $SelectedBuilds) {
        Invoke-PortableBuild $Profile
    }

    $Summary = [ordered]@{
        status = "passed"
        run_root = $RunRoot
        build_profiles = $SelectedBuilds
        steps = @($Steps)
    }
    $Summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
    Write-Output "Release verification passed. Summary: $SummaryPath"
} catch {
    $Summary = [ordered]@{
        status = "failed"
        run_root = $RunRoot
        error = "$_"
        steps = @($Steps)
    }
    $Summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
    Write-Error $_
    exit 1
} finally {
    Pop-Location
}
