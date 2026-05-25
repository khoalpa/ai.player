param(
    [string]$Python = "",
    [string]$OutputDir = "",
    [string[]]$AcceptedVulnerabilities = @("CVE-2025-69872"),
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
foreach ($Vulnerability in $AcceptedVulnerabilities) {
    if ($Vulnerability) {
        $AuditIgnores += @("--ignore-vuln", $Vulnerability)
    }
}

& $Python -m pip_audit --local @AuditIgnores --format json --output $LocalReport
$LocalAuditExitCode = $LASTEXITCODE

$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
if (Test-Path $RequirementsPath) {
    & $Python -m pip_audit -r $RequirementsPath @AuditIgnores --format json --output $RequirementsReport
    $RequirementsAuditExitCode = $LASTEXITCODE
} else {
    $RequirementsAuditExitCode = 0
}

Write-Output "Dependency audit reports written to: $OutputDir"
if ($AuditIgnores.Count -gt 0) {
    Write-Output "Accepted vulnerabilities ignored by policy: $($AcceptedVulnerabilities -join ', ')"
}

if ($LocalAuditExitCode -ne 0 -or $RequirementsAuditExitCode -ne 0) {
    throw "Dependency audit reported vulnerabilities. Review the JSON reports in $OutputDir."
}
