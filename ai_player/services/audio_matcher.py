from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services.ffmpeg import (
    extract_audio_range as ffmpeg_extract_audio_range,
)
from ai_player.services.ffmpeg import (
    probe_duration_seconds,
    run_ffmpeg,
    run_ffmpeg_cancelable,
)


@dataclass(frozen=True)
class AudioProfile:
    gender: str
    median_pitch_hz: float
    mean_volume_db: float | None
    duration_seconds: float


def profile_reference_audio(path: Path) -> AudioProfile:
    duration = audio_duration_seconds(path)
    return AudioProfile(
        gender=detect_speaker_gender(path),
        median_pitch_hz=_median_pitch_hz(path),
        mean_volume_db=mean_volume_db(path),
        duration_seconds=duration,
    )


def detect_speaker_gender(path: Path) -> str:
    pitch = _median_pitch_hz(path)
    if pitch <= 0:
        return "unknown"
    if pitch < 165:
        return "male"
    if pitch > 185:
        return "female"
    return "unknown"


def match_tts_to_reference(
    *,
    reference_path: Path,
    tts_path: Path,
    output_path: Path,
    target_duration_seconds: float,
    config: AppConfig,
    cancel_callback: Callable[[], bool] | None = None,
) -> Path:
    tts_duration = audio_duration_seconds(tts_path)
    filters: list[str] = []
    tempo = 1.0 + (config.dubbing_speed_percent / 100.0)
    if config.dubbing_auto_match_audio and tts_duration > 0.05 and target_duration_seconds > 0.05:
        auto_tempo = tts_duration / target_duration_seconds
        tempo *= max(config.dubbing_speed_min, min(config.dubbing_speed_max, auto_tempo))
    tempo = max(0.5, min(2.0, tempo))
    filters.extend(_atempo_filters(tempo))

    reference_volume = mean_volume_db(reference_path) if config.dubbing_auto_match_audio else None
    tts_volume = mean_volume_db(tts_path) if config.dubbing_auto_match_audio else None
    if reference_volume is not None and tts_volume is not None:
        gain = reference_volume - tts_volume
        gain = max(config.dubbing_volume_gain_min_db, min(config.dubbing_volume_gain_max_db, gain))
        if abs(gain) >= 0.5:
            filters.append(f"volume={gain:.2f}dB")

    if not filters:
        return tts_path

    args = [
        "-i",
        tts_path,
        "-af",
        ",".join(filters),
        "-ar",
        "44100",
        "-ac",
        "2",
        "-y",
        output_path,
    ]
    if cancel_callback is None:
        run_ffmpeg(args)
    else:
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    return tts_path


def extract_audio_range(
    source_path: Path,
    start_seconds: float,
    duration_seconds: float,
    output_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> None:
    ffmpeg_extract_audio_range(
        source_path,
        start_seconds,
        duration_seconds,
        output_path,
        cancel_callback=cancel_callback,
    )


def audio_duration_seconds(path: Path) -> float:
    return probe_duration_seconds(path)


def mean_volume_db(path: Path) -> float | None:
    try:
        completed = run_ffmpeg(
            [
                "-nostats",
                "-i",
                path,
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            loglevel=None,
            capture_output=True,
            text=True,
            check=False,
        )
        match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", completed.stderr)
        return float(match.group(1)) if match else None
    except Exception:
        return None


def _median_pitch_hz(path: Path) -> float:
    try:
        import librosa
        import numpy as np

        samples, sample_rate = librosa.load(str(path), sr=16000, mono=True)
        if samples.size < sample_rate // 10:
            return 0.0
        f0 = librosa.yin(samples, fmin=70, fmax=350, sr=sample_rate)
        voiced = f0[np.isfinite(f0)]
        voiced = voiced[(voiced >= 70) & (voiced <= 350)]
        if voiced.size == 0:
            return 0.0
        return float(np.median(voiced))
    except Exception:
        return 0.0


def _atempo_filters(tempo: float) -> list[str]:
    if not math.isfinite(tempo) or tempo <= 0:
        return []
    values: list[float] = []
    current = tempo
    while current > 2.0:
        values.append(2.0)
        current /= 2.0
    while current < 0.5:
        values.append(0.5)
        current /= 0.5
    values.append(current)
    return [f"atempo={value:.4f}" for value in values if abs(value - 1.0) >= 0.01]
