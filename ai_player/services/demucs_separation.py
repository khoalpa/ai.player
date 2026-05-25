from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from importlib.util import find_spec
from pathlib import Path

from ai_player.core.config import PROJECT_ROOT


class DemucsSeparationError(RuntimeError):
    pass


def demucs_available() -> bool:
    executable = demucs_executable()
    return (
        bool(_demucs_python())
        or _bundled_demucs_available()
        or Path(executable).is_file()
        or shutil.which(executable) is not None
    )


def demucs_command() -> list[str]:
    configured = os.getenv("AI_PLAYER_DEMUCS_PATH", "").strip()
    if configured:
        return [configured]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--demucs-runner"]
    python = _demucs_python()
    if python:
        return [python, "-m", "ai_player.services.demucs_runner"]
    return [demucs_executable()]


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


def demucs_two_stem_args(command_prefix: Sequence[str], input_path: Path, output_dir: Path, *, model: str) -> list[str]:
    return [
        *command_prefix,
        "-n",
        model,
        "--two-stems",
        "vocals",
        "-o",
        str(output_dir),
        str(input_path),
    ]


def _demucs_python() -> str:
    if getattr(sys, "frozen", False):
        return ""
    configured = os.getenv("AI_PLAYER_DEMUCS_PYTHON", "").strip()
    candidates = [
        Path(configured) if configured else None,
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate and candidate.is_file() and _python_has_demucs(str(candidate)):
            return str(candidate)
    return ""


def _bundled_demucs_available() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    return find_spec("demucs") is not None


def _python_has_demucs(python: str) -> bool:
    try:
        if Path(python).resolve() == Path(sys.executable).resolve() and not getattr(sys, "frozen", False):
            return find_spec("demucs") is not None
    except OSError:
        pass
    try:
        completed = subprocess.run(
            [python, "-c", "import demucs"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return False
    return completed.returncode == 0


def separate_vocals(input_path: Path, output_dir: Path, *, model: str = "htdemucs") -> Path:
    """Run Demucs and return the generated no-vocals path when available."""

    if not demucs_available():
        raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        demucs_two_stem_args(demucs_command(), input_path, output_dir, model=model),
        check=True,
    )
    stem_dir = output_dir / model / input_path.stem
    no_vocals = stem_dir / "no_vocals.wav"
    if not no_vocals.exists():
        raise DemucsSeparationError(f"Demucs did not create expected file: {no_vocals}")
    return no_vocals
