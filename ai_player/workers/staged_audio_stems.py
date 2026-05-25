from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services.demucs_separation import DemucsSeparationError, demucs_two_stem_args
from ai_player.services.source_voice_filter import (
    normalize_source_voice_filter_mode,
    normalize_source_voice_filter_model,
)
from ai_player.workers.export_media import fast_background_stem_args, fast_voice_stem_args
from ai_player.workers.export_utils import _nonempty_file

ProcessRunner = Callable[..., object]
FfmpegRunner = Callable[[list[object]], object]
ToWav = Callable[[Path, Path], object]
CancelCallback = Callable[[], bool]


def create_source_audio_stems(
    *,
    config: AppConfig,
    source_audio: Path,
    background_path: Path,
    voice_path: Path,
    temp_dir: Path | None,
    run_process: ProcessRunner,
    run_ffmpeg: FfmpegRunner,
    to_wav: ToWav,
    cancel_callback: CancelCallback,
    demucs_available: Callable[[], bool],
    demucs_command: Callable[[], list[str]],
    temp_missing_message: str,
) -> str:
    if not config.original_audio_voice_filter:
        copy_source_stems(source_audio, background_path, voice_path)
        return "disabled"
    mode = normalize_source_voice_filter_mode(config.original_audio_voice_filter_mode)
    if mode == "ai":
        if not demucs_available():
            raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")
        if temp_dir is None:
            raise RuntimeError(temp_missing_message)
        create_demucs_stems(
            config=config,
            source_audio=source_audio,
            background_path=background_path,
            voice_path=voice_path,
            temp_dir=temp_dir,
            run_process=run_process,
            to_wav=to_wav,
            cancel_callback=cancel_callback,
            demucs_command=demucs_command,
        )
        return "ai"
    create_fast_stems(source_audio, background_path, voice_path, run_ffmpeg=run_ffmpeg)
    return "fast"


def copy_source_stems(source_audio: Path, background_path: Path, voice_path: Path) -> None:
    shutil.copyfile(source_audio, background_path)
    shutil.copyfile(source_audio, voice_path)


def create_fast_stems(
    source_audio: Path,
    background_path: Path,
    voice_path: Path,
    *,
    run_ffmpeg: FfmpegRunner,
) -> None:
    run_ffmpeg(fast_background_stem_args(source_audio, background_path))
    run_ffmpeg(fast_voice_stem_args(source_audio, voice_path))


def create_demucs_stems(
    *,
    config: AppConfig,
    source_audio: Path,
    background_path: Path,
    voice_path: Path,
    temp_dir: Path,
    run_process: ProcessRunner,
    to_wav: ToWav,
    cancel_callback: CancelCallback,
    demucs_command: Callable[[], list[str]],
) -> None:
    model = normalize_source_voice_filter_model(config.original_audio_voice_filter_model)
    stems_dir = temp_dir / "demucs"
    run_process(
        demucs_two_stem_args(demucs_command(), source_audio, stems_dir, model=model),
        cancel_callback=cancel_callback,
    )
    stem_root = stems_dir / model / source_audio.stem
    no_vocals = stem_root / "no_vocals.wav"
    vocals = stem_root / "vocals.wav"
    if not _nonempty_file(no_vocals):
        raise RuntimeError(f"Demucs did not create expected file: {no_vocals}")
    to_wav(no_vocals, background_path)
    if _nonempty_file(vocals):
        to_wav(vocals, voice_path)
    else:
        shutil.copyfile(source_audio, voice_path)
