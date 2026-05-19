param(
    [string]$Python = "",
    [string]$BackupRoot = "",
    [string]$NamePrefix = "ai.player",
    [switch]$NoRuntime,
    [switch]$ExcludeGit
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
}
if (-not $BackupRoot) {
    $BackupRoot = Split-Path -Parent $ProjectRoot
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ZipPath = Join-Path $BackupRoot "$NamePrefix-backup-$Timestamp.zip"

$env:AI_PLAYER_BACKUP_PROJECT_ROOT = $ProjectRoot
$env:AI_PLAYER_BACKUP_ZIP_PATH = $ZipPath
$env:AI_PLAYER_BACKUP_NO_RUNTIME = if ($NoRuntime) { "1" } else { "0" }
$env:AI_PLAYER_BACKUP_EXCLUDE_GIT = if ($ExcludeGit) { "1" } else { "0" }

$PythonCode = @'
from __future__ import annotations

import fnmatch
import os
import zipfile
from pathlib import Path

root = Path(os.environ["AI_PLAYER_BACKUP_PROJECT_ROOT"]).resolve()
zip_path = Path(os.environ["AI_PLAYER_BACKUP_ZIP_PATH"]).resolve()
no_runtime = os.environ.get("AI_PLAYER_BACKUP_NO_RUNTIME") == "1"
exclude_git = os.environ.get("AI_PLAYER_BACKUP_EXCLUDE_GIT") == "1"

skip_dirs = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
}
if exclude_git:
    skip_dirs.add(".git")
if no_runtime:
    skip_dirs.update({"data", "dist", "models"})

skip_file_patterns = (
    "*.log",
    "*.pyc",
    "*.pyo",
    "*.tmp",
)

count = 0
total = 0
zip_path.parent.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [
            item
            for item in dirs
            if item not in skip_dirs and not (current_path / item).is_symlink()
        ]
        for filename in files:
            if any(fnmatch.fnmatch(filename, pattern) for pattern in skip_file_patterns):
                continue
            path = current_path / filename
            if path.is_symlink() or path.resolve() == zip_path:
                continue
            archive.write(path, path.relative_to(root))
            count += 1
            total += path.stat().st_size

print(f"Backup ready: {zip_path}")
print(f"Files: {count}")
print(f"Bytes: {total}")
'@

$PythonCode | & $Python -
