param(
    [string]$Python = "",
    [switch]$InstallDependencies,
    [string]$CodeSigningCertThumbprint = "",
    [string]$CodeSigningPfxPath = "",
    [securestring]$CodeSigningPfxPassword,
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$RequireSignature,
    [switch]$ListCodeSigningCerts,
    [switch]$SkipReleaseWorktreeCheck,
    [switch]$AllowInternalPlugins
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistRoot = Join-Path $ProjectRoot "dist"
$PortableRoot = Join-Path $DistRoot "portable\AI Player Lite"

if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

function Get-AvailableCodeSigningCertificates {
    $CertificateStores = @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")
    foreach ($Store in $CertificateStores) {
        Get-ChildItem -Path $Store -CodeSigningCert -ErrorAction SilentlyContinue |
            Select-Object `
                @{Name = "Store"; Expression = { $Store } },
                Subject,
                Thumbprint,
                NotAfter,
                EnhancedKeyUsageList
    }
}

function Get-CodeSigningCertificate {
    param(
        [string]$Thumbprint,
        [string]$PfxPath,
        [securestring]$PfxPassword,
        [switch]$Required
    )

    if ($Thumbprint -and $PfxPath) {
        throw "Use either -CodeSigningCertThumbprint or -CodeSigningPfxPath, not both."
    }

    if ($PfxPath) {
        if ($PfxPath -in @("<pfx-path>", "pfx-path", "<PFX_PATH>", "PFX_PATH")) {
            throw "Replace <pfx-path> with the path to a real .pfx or .p12 code-signing certificate."
        }

        $ResolvedPfxPath = (Resolve-Path -LiteralPath $PfxPath).Path
        if (-not $PfxPassword) {
            $PfxPassword = Read-Host -Prompt "Password for $ResolvedPfxPath" -AsSecureString
        }

        $Flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        $Certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($ResolvedPfxPath, $PfxPassword, $Flags)
        if (-not $Certificate.HasPrivateKey) {
            throw "The certificate in $ResolvedPfxPath does not contain a private key and cannot sign executables."
        }
        return $Certificate
    }

    if (-not $Thumbprint) {
        if (-not $Required) {
            return $null
        }

        $Certificates = @(Get-AvailableCodeSigningCertificates)
        if ($Certificates.Count -eq 1) {
            return Get-Item -LiteralPath (Join-Path $Certificates[0].Store $Certificates[0].Thumbprint)
        }
        if ($Certificates.Count -gt 1) {
            throw "Multiple code-signing certificates found. Run .\scripts\build_portable.ps1 -ListCodeSigningCerts, then pass the selected -CodeSigningCertThumbprint."
        }

        throw "No code-signing certificates found in CurrentUser\My or LocalMachine\My. Install an enterprise-approved code-signing certificate or pass -CodeSigningPfxPath, then rerun with -RequireSignature."
    }

    $NormalizedThumbprint = $Thumbprint -replace "\s", ""
    if ($NormalizedThumbprint -in @("<thumbprint>", "thumbprint", "<THUMBPRINT>", "THUMBPRINT")) {
        throw "Replace <thumbprint> with a real code-signing certificate thumbprint. Run: .\scripts\build_portable.ps1 -ListCodeSigningCerts"
    }

    $Certificate = Get-AvailableCodeSigningCertificates |
        Where-Object { $_.Thumbprint -eq $NormalizedThumbprint } |
        Select-Object -First 1
    if ($Certificate) {
        return Get-Item -LiteralPath (Join-Path $Certificate.Store $Certificate.Thumbprint)
    }

    throw "Code signing certificate not found in CurrentUser\My or LocalMachine\My: $Thumbprint"
}

function Set-BuildAuthenticodeSignature {
    param(
        [string]$Path,
        [AllowNull()]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [string]$TimestampUrl
    )

    if (-not $Certificate) {
        return
    }

    $SignArgs = @{
        FilePath = $Path
        Certificate = $Certificate
    }
    if ($TimestampUrl) {
        $SignArgs.TimestampServer = $TimestampUrl
    }

    $Signature = Set-AuthenticodeSignature @SignArgs
    if ($Signature.Status -ne "Valid") {
        throw "Failed to sign $Path. Status: $($Signature.Status). $($Signature.StatusMessage)"
    }
}

function Get-BuildSignableFiles {
    param([string]$Root)

    Get-ChildItem -LiteralPath $Root -Recurse -File |
        Where-Object { $_.Extension -in @(".exe", ".dll", ".pyd") } |
        Sort-Object FullName
}

function Set-BuildAuthenticodeSignatures {
    param(
        [string]$Root,
        [AllowNull()]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [string]$TimestampUrl
    )

    $SignableFiles = @(Get-BuildSignableFiles -Root $Root)
    if (-not $Certificate) {
        Write-Warning "No code-signing certificate was provided. $($SignableFiles.Count) PE files in the portable bundle will remain unsigned."
        Write-Warning "Enterprise Application Control policies can block unsigned builds. Rerun with -RequireSignature and a certificate for release artifacts."
        return
    }

    foreach ($File in $SignableFiles) {
        Set-BuildAuthenticodeSignature -Path $File.FullName -Certificate $Certificate -TimestampUrl $TimestampUrl
    }
    Write-Output "Signed $($SignableFiles.Count) PE files under $Root."
}

function Assert-ValidAuthenticodeSignature {
    param([string]$Path)

    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($Signature.Status -ne "Valid") {
        throw "Invalid or missing signature on $Path. Status: $($Signature.Status). $($Signature.StatusMessage)"
    }
}

function Assert-ValidAuthenticodeSignatures {
    param([string]$Root)

    $SignableFiles = @(Get-BuildSignableFiles -Root $Root)
    foreach ($File in $SignableFiles) {
        Assert-ValidAuthenticodeSignature -Path $File.FullName
    }
    Write-Output "Verified signatures for $($SignableFiles.Count) PE files under $Root."
}

if ($ListCodeSigningCerts) {
    $Certificates = @(Get-AvailableCodeSigningCertificates)
    if ($Certificates.Count -eq 0) {
        Write-Output "No code-signing certificates found in Cert:\CurrentUser\My or Cert:\LocalMachine\My."
        Write-Output "Install an enterprise-approved code-signing certificate, then rerun this command."
        exit 0
    }

    $Certificates | Format-Table -AutoSize Store, Subject, Thumbprint, NotAfter
    exit 0
}

function Test-TruthyEnvironmentValue {
    param([string]$Value)

    return $Value.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
}

function Assert-PublicBuildPluginScope {
    if ($AllowInternalPlugins) {
        return
    }

    $Blocked = New-Object System.Collections.Generic.List[string]
    if (Test-TruthyEnvironmentValue -Value "$env:AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS") {
        $Blocked.Add("AI_PLAYER_INCLUDE_EXTRA_YTDLP_PLUGINS")
    }
    if (Test-TruthyEnvironmentValue -Value "$env:AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN") {
        $Blocked.Add("AI_PLAYER_INCLUDE_PRIVATE_TELEGRAM_PLUGIN")
    }
    if ("$env:AI_PLAYER_EXTRA_YTDLP_HOSTS".Trim()) {
        $Blocked.Add("AI_PLAYER_EXTRA_YTDLP_HOSTS")
    }

    if ($Blocked.Count -gt 0) {
        $BlockedLines = $Blocked | ForEach-Object { "  - $_" }
        $Message = (@(
            "Public portable builds must not include internal/private plugin configuration.",
            "Unset these variables, or use .\scripts\build_internal.ps1 for internal artifacts:",
            ""
        ) + $BlockedLines) -join [Environment]::NewLine
        throw $Message
    }
}

Assert-PublicBuildPluginScope

if (-not $SkipReleaseWorktreeCheck) {
    $ReleaseWorktreeCheck = Join-Path $ProjectRoot "scripts\check_release_worktree.ps1"
    if (-not (Test-Path -LiteralPath $ReleaseWorktreeCheck)) {
        throw "Release worktree check script is missing: $ReleaseWorktreeCheck"
    }
    & $ReleaseWorktreeCheck -FailOnModified
    if ($LASTEXITCODE -ne 0) {
        throw "Release worktree check failed."
    }
} else {
    Write-Warning "Skipping release worktree check. Use this only for local development builds, not shared release artifacts."
}

$CodeSigningCertificate = Get-CodeSigningCertificate `
    -Thumbprint $CodeSigningCertThumbprint `
    -PfxPath $CodeSigningPfxPath `
    -PfxPassword $CodeSigningPfxPassword `
    -Required:$RequireSignature

if ($InstallDependencies) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e "$ProjectRoot[packaging,offline-ai,gpu,audio-separation]"
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: .\scripts\build_portable.ps1 -InstallDependencies"
}

if (Test-Path $PortableRoot) {
    Remove-Item -LiteralPath $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    "$ProjectRoot\AI Player.spec"

$AppDist = Join-Path $DistRoot "AI Player"
if (-not (Test-Path $AppDist)) {
    throw "PyInstaller did not create expected app folder: $AppDist"
}

$AppExe = Join-Path $AppDist "AI Player.exe"
if (-not (Test-Path $AppExe)) {
    throw "PyInstaller did not create expected app executable: $AppExe"
}
Set-BuildAuthenticodeSignatures -Root $AppDist -Certificate $CodeSigningCertificate -TimestampUrl $TimestampServer

Copy-Item -LiteralPath $AppDist -Destination $PortableRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $PortableRoot -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination $PortableRoot -Force

# Bootstrap the separate TTS environment on the destination machine; venvs are not relocatable.
$PortableScripts = Join-Path $PortableRoot "scripts"
New-Item -ItemType Directory -Force -Path $PortableScripts | Out-Null
foreach ($Name in @("setup_vieneu_runtime.ps1", "prepare_vieneu_runtime.py", "download_vieneu_tts_models.ps1", "download_vieneu_v3.py")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $Name) -Destination $PortableScripts -Force
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot "requirements-vieneu.txt") -Destination $PortableRoot -Force
$RuntimeSources = Get-Content -LiteralPath (Join-Path $PSScriptRoot "vieneu_runtime_sources.json") -Raw | ConvertFrom-Json
foreach ($Relative in $RuntimeSources) {
    $Destination = Join-Path $PortableRoot ("ai_player\" + $Relative)
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ("ai_player\" + $Relative)) -Destination $Destination -Force
}

$PortableExe = Join-Path $PortableRoot "AI Player\AI Player.exe"
if ($RequireSignature) {
    if (-not (Test-Path $PortableExe)) {
        throw "Portable executable is missing: $PortableExe"
    }
    Assert-ValidAuthenticodeSignatures -Root (Join-Path $PortableRoot "AI Player")
}

$InternalRoot = Join-Path $PortableRoot "AI Player\_internal"
$PortablePruneDirs = @(
    "pyarrow\tests",
    "sklearn\datasets\tests",
    "spacy\tests",
    "thinc\tests",
    "thinc\extra\tests"
)

foreach ($RelativePath in $PortablePruneDirs) {
    $Target = Join-Path $InternalRoot $RelativePath
    if (Test-Path $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

$launcher = Join-Path $PortableRoot "Run AI Player.bat"
@'
@echo off
set "APP_ROOT=%~dp0"
set "AI_PLAYER_PROJECT_ROOT=%APP_ROOT%"
if exist "%APP_ROOT%tools\ffmpeg\bin" set "PATH=%APP_ROOT%tools\ffmpeg\bin;%PATH%"
if exist "%APP_ROOT%tools\ffmpeg" set "PATH=%APP_ROOT%tools\ffmpeg;%PATH%"
start "" "%APP_ROOT%AI Player\AI Player.exe"
'@ | Set-Content -LiteralPath $launcher -Encoding ASCII

Write-Output "Portable Lite ready: $PortableRoot"
