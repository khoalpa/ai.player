param(
    [string[]]$AllowUntrackedPath = @(),
    [switch]$FailOnModified
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $ProjectRoot
try {
    $Git = Get-Command git -ErrorAction Stop
    $Untracked = & $Git.Source ls-files -o --exclude-standard
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-files failed."
    }

    $Allowed = @{}
    foreach ($Path in $AllowUntrackedPath) {
        $Normalized = ($Path -replace "\\", "/").Trim("/")
        if ($Normalized) {
            $Allowed[$Normalized.ToLowerInvariant()] = $true
        }
    }

    $SourceExtensions = @(
        ".bat",
        ".cmd",
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".spec",
        ".toml",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml"
    )
    $Blocked = New-Object System.Collections.Generic.List[string]
    foreach ($Path in $Untracked) {
        $Normalized = ($Path -replace "\\", "/").Trim("/")
        if (-not $Normalized) {
            continue
        }
        if ($Allowed.ContainsKey($Normalized.ToLowerInvariant())) {
            continue
        }
        $Extension = [System.IO.Path]::GetExtension($Normalized).ToLowerInvariant()
        if ($Normalized.ToLowerInvariant().StartsWith("plugins/") -or $SourceExtensions -contains $Extension) {
            $Blocked.Add($Normalized)
        }
    }

    if ($Blocked.Count -gt 0) {
        $BlockedLines = $Blocked | ForEach-Object { "  - $_" }
        $Message = (@(
            "Release worktree check failed: untracked source/plugin files are present.",
            "Commit intended files, move private/scratch files under ignored runtime paths, or pass -AllowUntrackedPath for an explicit release exception.",
            ""
        ) + $BlockedLines) -join [Environment]::NewLine
        throw $Message
    }

    $ArtifactInventoryPath = Join-Path $ProjectRoot "docs\release_artifact_inventory.md"
    $ArtifactInventory = if (Test-Path $ArtifactInventoryPath) {
        Get-Content -LiteralPath $ArtifactInventoryPath -Raw
    } else {
        ""
    }
    $TrackedFiles = & $Git.Source ls-files
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-files failed."
    }
    $ArtifactExtensions = @(
        ".7z",
        ".dll",
        ".dylib",
        ".exe",
        ".msi",
        ".pdf",
        ".pyd",
        ".so",
        ".zip"
    )
    $UndocumentedArtifacts = New-Object System.Collections.Generic.List[string]
    foreach ($Path in $TrackedFiles) {
        $Normalized = ($Path -replace "\\", "/").Trim("/")
        if (-not $Normalized) {
            continue
        }
        $Extension = [System.IO.Path]::GetExtension($Normalized).ToLowerInvariant()
        if ($ArtifactExtensions -notcontains $Extension) {
            continue
        }
        $IsRootArtifact = -not $Normalized.Contains("/")
        $IsBundledToolArtifact = $Normalized.ToLowerInvariant().StartsWith("tools/")
        if (-not ($IsRootArtifact -or $IsBundledToolArtifact)) {
            continue
        }
        $InventoryToken = "``$Normalized``"
        if (-not $ArtifactInventory.Contains($InventoryToken)) {
            $UndocumentedArtifacts.Add($Normalized)
        }
    }

    if ($UndocumentedArtifacts.Count -gt 0) {
        $ArtifactLines = $UndocumentedArtifacts | ForEach-Object { "  - $_" }
        $Message = (@(
            "Release worktree check failed: tracked root/tool binary artifacts are missing from docs\release_artifact_inventory.md.",
            "Document the artifact, owner, license/source, and release decision before sharing a public build.",
            ""
        ) + $ArtifactLines) -join [Environment]::NewLine
        throw $Message
    }

    if ($FailOnModified) {
        $Modified = & $Git.Source status --porcelain
        if ($LASTEXITCODE -ne 0) {
            throw "git status failed."
        }
        $Unexpected = @($Modified | Where-Object { $_ -and -not $_.StartsWith("?? ") })
        if ($Unexpected.Count -gt 0) {
            $UnexpectedLines = $Unexpected | ForEach-Object { "  - $_" }
            $Message = (@(
                "Release worktree check failed: tracked file modifications are present.",
                "Commit, stash, or intentionally remove these changes before creating the release artifact.",
                ""
            ) + $UnexpectedLines) -join [Environment]::NewLine
            throw $Message
        }
    }

    Write-Output "Release worktree check passed."
} finally {
    Pop-Location
}
