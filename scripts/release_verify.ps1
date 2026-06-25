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
    function Get-StepSummary {
        return @($Steps | ForEach-Object { $_ })
    }

    function Write-ReleaseSummary {
        param(
            [string]$Status,
            [string]$ErrorMessage = "",
            [object[]]$BuildProfileList = @()
        )

        $Summary = [ordered]@{
            status = $Status
            run_root = $RunRoot
            build_profiles = @($BuildProfileList)
            steps = Get-StepSummary
        }
        if ($ErrorMessage) {
            $Summary["error"] = $ErrorMessage
        }
        $Summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
    }

    function Invoke-ReleaseStep {
        param(
            [string]$Name,
            [string]$FilePath,
            [string[]]$Arguments
        )

        $LogPath = Join-Path $RunRoot "$Name.log"
        Write-Output "==> $Name"
        $Started = Get-Date
        $Output = @()
        $ExitCode = 0
        try {
            $Output = & $FilePath @Arguments 2>&1
            $ExitCode = if ($null -ne $global:LASTEXITCODE) { $global:LASTEXITCODE } else { 0 }
        } catch {
            $Output = @($Output) + @("$_")
            $ExitCode = 1
        }
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
            Invoke-ReleaseStep -Name "install-lite" -FilePath $Python -Arguments @(
                "-m",
                "pip",
                "install",
                "-e",
                ".[dev,packaging]"
            )
        } elseif ($Profile -eq "OfflineCpu") {
            Invoke-ReleaseStep -Name "install-offline-cpu" -FilePath $Python -Arguments @(
                "-m",
                "pip",
                "install",
                "-e",
                ".[dev,packaging,offline-ai,audit]"
            )
        } elseif ($Profile -eq "Gpu") {
            Invoke-ReleaseStep -Name "install-gpu" -FilePath $Python -Arguments @(
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
        $BuildScript = Join-Path $ProjectRoot "scripts\build_portable.ps1"
        $BuildCommandArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BuildScript) + $BuildArgs
        Invoke-ReleaseStep `
            -Name "build-$($Profile.ToLowerInvariant())" `
            -FilePath "powershell.exe" `
            -Arguments $BuildCommandArgs
        Invoke-ReleaseStep `
            -Name "launch-$($Profile.ToLowerInvariant())" `
            -FilePath (Join-Path $ProjectRoot "scripts\smoke_launch_app.ps1") `
            -Arguments @(
            "-AppPath",
            "dist\portable\AI Player Lite\AI Player\AI Player.exe",
            "-Seconds",
            "8"
        )
    }

    Invoke-ReleaseStep `
        -Name "worktree" `
        -FilePath (Join-Path $ProjectRoot "scripts\check_release_worktree.ps1") `
        -Arguments @("-FailOnModified")
    Invoke-ReleaseStep -Name "ruff" -FilePath $Python -Arguments @("-m", "ruff", "check", ".")
    if (-not $SkipPytest) {
        Invoke-ReleaseStep -Name "pytest" -FilePath $Python -Arguments @("-m", "pytest", "-q")
    }
    Invoke-ReleaseStep -Name "pip-check" -FilePath $Python -Arguments @("-m", "pip", "check")
    Invoke-ReleaseStep -Name "runtime-doctor" -FilePath $Python -Arguments @(".\scripts\runtime_doctor.py", "--ci")
    Invoke-ReleaseStep -Name "workflow-smoke" -FilePath $Python -Arguments @(
        ".\scripts\workflow_smoke_check.py",
        "--output",
        (Join-Path $RunRoot "workflow-smoke-current.json")
    )
    Invoke-ReleaseStep `
        -Name "release-smoke" `
        -FilePath $Python `
        -Arguments @("-m", "pytest", "tests\test_release_smoke.py", "-q")

    $BuildOrder = @("Lite", "OfflineCpu", "Gpu")
    $SelectedBuilds = @($BuildOrder | Where-Object { $BuildProfiles -contains $_ })
    foreach ($Profile in $SelectedBuilds) {
        Invoke-PortableBuild $Profile
    }

    Write-ReleaseSummary -Status "passed" -BuildProfileList $SelectedBuilds
    Write-Output "Release verification passed. Summary: $SummaryPath"
} catch {
    Write-ReleaseSummary -Status "failed" -ErrorMessage "$_"
    Write-Error $_
    exit 1
} finally {
    Pop-Location
}
