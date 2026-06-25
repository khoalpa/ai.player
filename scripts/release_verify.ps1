param(
    [string]$Python = "",
    [ValidateSet("Lite", "OfflineCpu", "Gpu")]
    [string[]]$BuildProfiles = @(),
    [switch]$InstallDependencies,
    [switch]$SkipPytest,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunRoot = Join-Path $ProjectRoot "data\tmp\release-verify\$RunStamp"
$SummaryPath = Join-Path $RunRoot "summary.json"
$Steps = New-Object System.Collections.Generic.List[object]
$ProfileSummaries = New-Object System.Collections.Generic.List[object]

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
            profile_summaries = @($ProfileSummaries | ForEach-Object { $_ })
            steps = Get-StepSummary
        }
        if ($ErrorMessage) {
            $Summary["error"] = $ErrorMessage
        }
        $Summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
    }

    function Get-BuildProfileInfo {
        param([string]$Profile)

        $ArtifactPath = Join-Path $ProjectRoot "dist\portable\AI Player Lite"
        $AppPath = Join-Path $ArtifactPath "AI Player\AI Player.exe"
        if ($Profile -eq "Lite") {
            return [ordered]@{
                profile = "Lite"
                scope = "UI/document/URL/Edge TTS"
                dependency_profile = "dev,packaging"
                artifact_path = $ArtifactPath
                app_path = $AppPath
            }
        }
        if ($Profile -eq "OfflineCpu") {
            return [ordered]@{
                profile = "OfflineCpu"
                scope = "ASR/NLLB/VieNeu local"
                dependency_profile = "dev,packaging,offline-ai,audit"
                artifact_path = $ArtifactPath
                app_path = $AppPath
            }
        }
        if ($Profile -eq "Gpu") {
            return [ordered]@{
                profile = "Gpu"
                scope = "CUDA/Demucs/source separation"
                dependency_profile = "dev,packaging,offline-ai,gpu,audio-separation,audit"
                artifact_path = $ArtifactPath
                app_path = $AppPath
            }
        }
        throw "Unknown build profile: $Profile"
    }

    function Write-BuildProfileSummary {
        param(
            [string]$Profile,
            [string]$Status
        )

        $Info = Get-BuildProfileInfo $Profile
        $StepPrefix = $Profile.ToLowerInvariant()
        $InstallStep = if ($Profile -eq "OfflineCpu") { "install-offline-cpu" } else { "install-$StepPrefix" }
        $ProfileSteps = @(
            Get-StepSummary |
                Where-Object { $_.name -in @($InstallStep, "build-$StepPrefix", "launch-$StepPrefix") }
        )
        $ProfileSummaryPath = Join-Path $RunRoot "profile-$StepPrefix-summary.json"
        $ProfileSummary = [ordered]@{
            status = $Status
            run_root = $RunRoot
            summary = $ProfileSummaryPath
            profile = $Info
            steps = $ProfileSteps
        }
        $ProfileSummary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ProfileSummaryPath -Encoding UTF8
        $ProfileSummaries.Add([ordered]@{
            profile = $Profile
            status = $Status
            scope = $Info["scope"]
            summary = $ProfileSummaryPath
            artifact_path = $Info["artifact_path"]
            app_path = $Info["app_path"]
        }) | Out-Null
    }

    function Join-ProcessArguments {
        param([string[]]$Values)

        $Quoted = foreach ($Value in $Values) {
            $Text = "$Value"
            if (-not $Text) {
                '""'
            } elseif ($Text -match '[\s"]') {
                '"' + $Text.Replace('"', '\"') + '"'
            } else {
                $Text
            }
        }
        return ($Quoted -join " ")
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
        $Stdout = ""
        $Stderr = ""
        try {
            $ProcessFilePath = $FilePath
            $ProcessArguments = $Arguments
            if ([System.IO.Path]::GetExtension($FilePath).Equals(".ps1", [System.StringComparison]::OrdinalIgnoreCase)) {
                $ProcessFilePath = "powershell.exe"
                $ProcessArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $FilePath) + $Arguments
            }
            $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
            $StartInfo.FileName = $ProcessFilePath
            $StartInfo.WorkingDirectory = $ProjectRoot
            $StartInfo.UseShellExecute = $false
            $StartInfo.RedirectStandardOutput = $true
            $StartInfo.RedirectStandardError = $true
            $StartInfo.Arguments = Join-ProcessArguments $ProcessArguments
            $Process = [System.Diagnostics.Process]::new()
            $Process.StartInfo = $StartInfo
            if (-not $Process.Start()) {
                throw "Failed to start $FilePath"
            }
            $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
            $StderrTask = $Process.StandardError.ReadToEndAsync()
            $Process.WaitForExit()
            $Stdout = $StdoutTask.Result
            $Stderr = $StderrTask.Result
            $ExitCode = $Process.ExitCode
        } catch {
            $Stderr = "$Stderr`n$_"
            $ExitCode = 1
        }
        $Output = @()
        if ($Stdout) {
            $Output += $Stdout.TrimEnd()
        }
        if ($Stderr) {
            $Output += $Stderr.TrimEnd()
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

        $ProfileInfo = Get-BuildProfileInfo $Profile
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
            $ProfileInfo["app_path"],
            "-Seconds",
            "8"
        )
        Write-BuildProfileSummary -Profile $Profile -Status "passed"
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
