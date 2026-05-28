from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import soundfile as sf


def main() -> None:
    _prefer_resolved_media_tools()
    _patch_torchaudio_save()
    from demucs.separate import main as demucs_main

    demucs_main()


def _prefer_resolved_media_tools() -> None:
    from ai_player.services.ffmpeg import ffmpeg_executable, ffprobe_executable

    paths = [Path(ffmpeg_executable()).parent, Path(ffprobe_executable()).parent]
    directories = [str(path) for path in dict.fromkeys(paths) if path.is_dir()]
    if not directories:
        return
    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*directories, current_path] if current_path else directories)


def _patch_torchaudio_save() -> None:
    import demucs.audio
    import torchaudio

    torchaudio.save = _soundfile_save
    demucs.audio.ta.save = _soundfile_save


def _soundfile_save(
    uri: str | Path,
    src: Any,
    sample_rate: int,
    channels_first: bool = True,
    format: str | None = None,
    encoding: str | None = None,
    bits_per_sample: int | None = None,
    **_kwargs: Any,
) -> None:
    data = src.detach().cpu().numpy() if hasattr(src, "detach") else src
    if channels_first and getattr(data, "ndim", 0) == 2:
        data = data.T
    subtype = _soundfile_subtype(uri, format, encoding, bits_per_sample)
    sf.write(str(uri), data, int(sample_rate), subtype=subtype)


def _soundfile_subtype(
    uri: str | Path,
    format_hint: str | None,
    encoding: str | None,
    bits_per_sample: int | None,
) -> str | None:
    suffix = Path(uri).suffix.lower()
    if suffix == ".wav" or str(format_hint or "").lower() == "wav":
        if str(encoding or "").upper() == "PCM_F":
            return "FLOAT"
        if bits_per_sample == 24:
            return "PCM_24"
        if bits_per_sample == 32:
            return "PCM_32"
        return "PCM_16"
    if suffix == ".flac" and bits_per_sample == 24:
        return "PCM_24"
    return None


if __name__ == "__main__":
    sys.exit(main())
