param(
    [string]$Python = "",
    [string]$OutputDir = "",
    [string[]]$AcceptedVulnerabilities = @("CVE-2025-69872"),
    [int]$Retries = 2,
    [switch]$ReviewAcceptedVulnerabilities,
    [switch]$InstallTools
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "data\tmp\dependency-audit"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$AuditCacheDir = Join-Path $OutputDir "cache-$PID"
New-Item -ItemType Directory -Force -Path $AuditCacheDir | Out-Null

if ($InstallTools) {
    & $Python -m pip install -e "$ProjectRoot[audit]"
}

& $Python -m pip_audit --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "pip-audit is not installed. Run: .\scripts\audit_dependencies.ps1 -InstallTools"
}

$LocalReport = Join-Path $OutputDir "pip-audit-local.json"
$RequirementsReport = Join-Path $OutputDir "pip-audit-requirements.json"

$AuditIgnores = @()
if (-not $ReviewAcceptedVulnerabilities) {
    foreach ($Vulnerability in $AcceptedVulnerabilities) {
        if ($Vulnerability) {
            $AuditIgnores += @("--ignore-vuln", $Vulnerability)
        }
    }
}

function Invoke-PipAudit {
    param(
        [object[]]$Arguments,
        [string]$ReportPath
    )

    $Attempt = 0
    do {
        $Attempt += 1
        if ($ReportPath -and (Test-Path $ReportPath)) {
            Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
        }
        $PreviousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $Python -m pip_audit `
                --cache-dir $AuditCacheDir `
                --timeout 60 `
                --progress-spinner off `
                @Arguments *> $null
            $ExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }
        if ($ExitCode -eq 0 -or (Test-AuditReportJson -Path $ReportPath) -or $Attempt -gt $Retries) {
            return $ExitCode
        }
        Write-Warning "pip-audit failed with exit code $ExitCode; retrying ($Attempt/$Retries)..."
        Start-Sleep -Seconds 2
    } while ($true)
}

function Test-AuditReportJson {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $false
    }
    try {
        $Report = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        return $null -ne $Report.dependencies
    } catch {
        return $false
    }
}

function Get-AuditFindings {
    param([string[]]$ReportPaths)

    $Findings = @()
    foreach ($Path in $ReportPaths) {
        if (-not (Test-Path $Path)) {
            continue
        }
        $Report = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($Dependency in $Report.dependencies) {
            $Vulnerabilities = @($Dependency.vulns) | Where-Object { $_ -and $_.id }
            foreach ($Vulnerability in $Vulnerabilities) {
                $Findings += [PSCustomObject]@{
                    Package = $Dependency.name
                    Version = $Dependency.version
                    Vulnerability = $Vulnerability.id
                    Report = (Split-Path -Leaf $Path)
                }
            }
        }
    }
    return $Findings
}

$LocalAuditExitCode = Invoke-PipAudit -Arguments (@("--local") + $AuditIgnores + @("--format", "json", "--output", $LocalReport)) -ReportPath $LocalReport

$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
if (Test-Path $RequirementsPath) {
    $RequirementsAuditExitCode = Invoke-PipAudit -Arguments (@("-r", $RequirementsPath) + $AuditIgnores + @("--format", "json", "--output", $RequirementsReport)) -ReportPath $RequirementsReport
} else {
    $RequirementsAuditExitCode = 0
}

Write-Output "Dependency audit reports written to: $OutputDir"
if ($AuditIgnores.Count -gt 0) {
    Write-Output "Accepted vulnerabilities ignored by policy: $($AcceptedVulnerabilities -join ', ')"
}

if ($ReviewAcceptedVulnerabilities) {
    $Findings = @(Get-AuditFindings -ReportPaths @($LocalReport, $RequirementsReport))
    $Unexpected = @(
        $Findings |
            Where-Object { $_.Vulnerability -notin $AcceptedVulnerabilities }
    )
    if ($Findings.Count -eq 0) {
        Write-Output "Accepted vulnerability review: no vulnerabilities reported."
    } else {
        Write-Output "Accepted vulnerability review:"
        $Findings |
            Sort-Object Vulnerability, Package, Report |
            Format-Table -AutoSize Report, Package, Version, Vulnerability |
            Out-String |
            ForEach-Object { $_.TrimEnd() } |
            Where-Object { $_ } |
            Write-Output
    }
    if ($Unexpected.Count -gt 0) {
        throw "Dependency audit reported vulnerabilities outside the accepted policy."
    }
    exit 0
}

if ($LocalAuditExitCode -ne 0 -or $RequirementsAuditExitCode -ne 0) {
    throw "Dependency audit reported vulnerabilities. Review the JSON reports in $OutputDir."
}
