from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ai_player.core.config import PROJECT_ROOT


class DemucsSeparationError(RuntimeError):
    pass


def demucs_available() -> bool:
    executable = demucs_executable()
    return Path(executable).is_file() or shutil.which(executable) is not None


def demucs_executable() -> str:
    configured = os.getenv("AI_PLAYER_DEMUCS_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        PROJECT_ROOT / ".venv" / "Scripts" / "demucs.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return str(candidate)
    return shutil.which("demucs") or "demucs"


def separate_vocals(input_path: Path, output_dir: Path, *, model: str = "htdemucs") -> Path:
    """Run Demucs and return the generated no-vocals path when available."""

    if not demucs_available():
        raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            demucs_executable(),
            "-n",
            model,
            "--two-stems",
            "vocals",
            "-o",
            str(output_dir),
            str(input_path),
        ],
        check=True,
    )
    stem_dir = output_dir / model / input_path.stem
    no_vocals = stem_dir / "no_vocals.wav"
    if not no_vocals.exists():
        raise DemucsSeparationError(f"Demucs did not create expected file: {no_vocals}")
    return no_vocals
