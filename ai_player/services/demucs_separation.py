from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class DemucsSeparationError(RuntimeError):
    pass


def demucs_available() -> bool:
    return shutil.which("demucs") is not None


def separate_vocals(input_path: Path, output_dir: Path, *, model: str = "htdemucs") -> Path:
    """Run Demucs and return the generated no-vocals path when available."""

    if not demucs_available():
        raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "demucs",
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
