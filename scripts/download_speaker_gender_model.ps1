$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$env:AI_PLAYER_PROJECT_ROOT = $ProjectRoot
@'
import os
from pathlib import Path
from huggingface_hub import snapshot_download

repo_id = "prithivMLmods/Common-Voice-Gender-Detection"
project_root = Path(os.environ["AI_PLAYER_PROJECT_ROOT"])
local_dir = project_root / "models" / "speaker_gender" / "common-voice-gender-detection"
local_dir.mkdir(parents=True, exist_ok=True)
snapshot_download(
    repo_id=repo_id,
    local_dir=str(local_dir),
    allow_patterns=[
        "config.json",
        "preprocessor_config.json",
        "model.safetensors",
        "pytorch_model.bin",
        "README.md",
    ],
)
print(f"Speaker gender model ready: {local_dir}")
'@ | & $Python -
