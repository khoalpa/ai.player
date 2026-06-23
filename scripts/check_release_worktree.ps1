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
