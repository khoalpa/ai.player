param(
    [string]$ExecutablePath = "",
    [string]$OutputDir = "",
    [guid]$SupplementsBasePolicyID = [guid]::Empty,
    [string]$PolicyName = "AI Player Local Code Signing Trust",
    [string]$ExpectedSignerThumbprint = "",
    [switch]$Deploy
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ExecutablePath) {
    $ExecutablePath = Join-Path $ProjectRoot "dist\portable\AI Player Lite\AI Player\AI Player.exe"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "data\tmp\wdac\ai-player-signer"
}

function Test-IsAdministrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-LatestAiPlayerBlockPolicyId {
    param([string]$ExecutableName)

    $Pattern = [regex]::Escape($ExecutableName)
    $PolicyPattern = "Policy ID:\{(?<policyId>[0-9a-fA-F-]+)\}"
    $Events = Get-WinEvent -LogName "Microsoft-Windows-CodeIntegrity/Operational" -MaxEvents 500 -ErrorAction SilentlyContinue
    foreach ($Event in $Events) {
        if ($Event.Message -notmatch $Pattern) {
            continue
        }
        if ($Event.Message -match $PolicyPattern) {
            return [guid]$Matches.policyId
        }
    }
    return [guid]::Empty
}

$ResolvedExe = (Resolve-Path -LiteralPath $ExecutablePath).Path
$Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedExe
if ($Signature.Status -ne "Valid") {
    throw "Executable signature is not valid: $ResolvedExe. Status: $($Signature.Status). $($Signature.StatusMessage)"
}
if (-not $Signature.SignerCertificate) {
    throw "Executable does not expose a signer certificate: $ResolvedExe"
}

$SignerThumbprint = $Signature.SignerCertificate.Thumbprint
if ($ExpectedSignerThumbprint) {
    $Expected = $ExpectedSignerThumbprint -replace "\s", ""
    if ($SignerThumbprint -ne $Expected) {
        throw "Signer thumbprint mismatch. Expected $Expected but found $SignerThumbprint."
    }
}

if ($SupplementsBasePolicyID -eq [guid]::Empty) {
    $SupplementsBasePolicyID = Get-LatestAiPlayerBlockPolicyId -ExecutableName (Split-Path -Leaf $ResolvedExe)
}
if ($SupplementsBasePolicyID -eq [guid]::Empty) {
    throw "Could not infer the enforced WDAC base policy ID from CodeIntegrity logs. Pass -SupplementsBasePolicyID after running CiTool.exe --list-policies from an elevated prompt."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$ResolvedOutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
$PolicyXml = Join-Path $ResolvedOutputDir "ai-player-signer-policy.xml"
$PolicyBin = Join-Path $ResolvedOutputDir "ai-player-signer-policy.cip"
Remove-Item -LiteralPath $PolicyXml, $PolicyBin -Force -ErrorAction SilentlyContinue

$Rule = New-CIPolicyRule -DriverFilePath $ResolvedExe -Level Publisher -Fallback Hash
New-CIPolicy -FilePath $PolicyXml -Rules $Rule -UserPEs -MultiplePolicyFormat | Out-Host
Set-CIPolicyIdInfo -FilePath $PolicyXml -PolicyName $PolicyName -ResetPolicyID
Set-CIPolicyIdInfo -FilePath $PolicyXml -SupplementsBasePolicyID $SupplementsBasePolicyID

# A signer allow supplemental policy should add allow rules, not switch the base
# policy into audit mode.
Set-RuleOption -FilePath $PolicyXml -Option 3 -Delete -ErrorAction SilentlyContinue

ConvertFrom-CIPolicy -XmlFilePath $PolicyXml -BinaryFilePath $PolicyBin | Out-Host

$Summary = [ordered]@{
    executable = $ResolvedExe
    signer_subject = $Signature.SignerCertificate.Subject
    signer_thumbprint = $SignerThumbprint
    supplements_base_policy_id = $SupplementsBasePolicyID
    policy_xml = $PolicyXml
    policy_cip = $PolicyBin
    deployed = $false
}

if ($Deploy) {
    if (-not (Test-IsAdministrator)) {
        throw "Deploy requires an elevated PowerShell session. Rerun as Administrator or deploy manually with CiTool.exe --update-policy `"$PolicyBin`"."
    }

    & "$env:WINDIR\System32\CiTool.exe" --update-policy $PolicyBin --json
    if ($LASTEXITCODE -ne 0) {
        throw "CiTool.exe --update-policy failed with exit code $LASTEXITCODE."
    }
    & "$env:WINDIR\System32\CiTool.exe" --refresh --json
    if ($LASTEXITCODE -ne 0) {
        throw "CiTool.exe --refresh failed with exit code $LASTEXITCODE."
    }
    $Summary.deployed = $true
}

[pscustomobject]$Summary | Format-List
if (-not $Deploy) {
    Write-Output ""
    Write-Output "Generated WDAC supplemental policy only. To deploy, rerun from elevated PowerShell:"
    Write-Output ".\scripts\create_wdac_ai_player_policy.ps1 -Deploy -ExpectedSignerThumbprint $SignerThumbprint"
}
