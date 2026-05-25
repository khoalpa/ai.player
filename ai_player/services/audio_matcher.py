from __future__ import annotations

import logging
import math
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import positive_int as _core_positive_int
from ai_player.services.ffmpeg import (
    extract_audio_range as ffmpeg_extract_audio_range,
)
from ai_player.services.ffmpeg import (
    probe_duration_seconds,
    run_ffmpeg,
    run_ffmpeg_cancelable,
)

_LOGGER = logging.getLogger(__name__)
_DURATION_FALLBACK_WARNING_EMITTED = False
_MATCH_OUTPUT_SAMPLE_RATE = 44100
_MATCH_OUTPUT_CHANNELS = 2
_NATURAL_TEMPO_MIN = 0.92
_NATURAL_TEMPO_MAX = 1.12


@dataclass(frozen=True)
class AudioProfile:
    gender: str
    median_pitch_hz: float
    mean_volume_db: float | None
    duration_seconds: float
    pitch_iqr_hz: float = 0.0
    voiced_ratio: float = 0.0
    gender_confidence: float = 0.0
    detector: str = "pitch"


@dataclass(frozen=True)
class PitchStats:
    median_hz: float
    iqr_hz: float
    voiced_ratio: float


@dataclass(frozen=True)
class AudioMatchPlan:
    filters: tuple[str, ...]
    tempo: float
    gain_db: float | None
    tts_duration_seconds: float | None
    reference_volume_db: float | None
    tts_volume_db: float | None


def profile_reference_audio(path: Path) -> AudioProfile:
    duration = audio_duration_seconds(path)
    pitch_stats = _pitch_stats(path)
    gender, confidence = _classify_pitch_gender(pitch_stats, duration)
    return AudioProfile(
        gender=gender,
        median_pitch_hz=pitch_stats.median_hz,
        mean_volume_db=mean_volume_db(path),
        duration_seconds=duration,
        pitch_iqr_hz=pitch_stats.iqr_hz,
        voiced_ratio=pitch_stats.voiced_ratio,
        gender_confidence=confidence,
    )


def detect_speaker_gender(path: Path) -> str:
    duration = audio_duration_seconds(path)
    gender, _confidence = _classify_pitch_gender(_pitch_stats(path), duration)
    return gender


def match_tts_to_reference(
    *,
    reference_path: Path,
    tts_path: Path,
    output_path: Path,
    target_duration_seconds: float,
    config: AppConfig,
    cancel_callback: Callable[[], bool] | None = None,
) -> Path:
    plan = _build_audio_match_plan(
        reference_path=reference_path,
        tts_path=tts_path,
        target_duration_seconds=target_duration_seconds,
        config=config,
    )
    if not plan.filters:
        return tts_path

    args = [
        "-i",
        tts_path,
        "-af",
        ",".join(plan.filters),
        "-ar",
        str(_MATCH_OUTPUT_SAMPLE_RATE),
        "-ac",
        str(_MATCH_OUTPUT_CHANNELS),
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


def _build_audio_match_plan(
    *,
    reference_path: Path,
    tts_path: Path,
    target_duration_seconds: float,
    config: AppConfig,
) -> AudioMatchPlan:
    filters: list[str] = []
    speed_percent = _finite_float(config.dubbing_speed_percent, 0.0)
    target_duration = _finite_float(target_duration_seconds, 0.0)
    tempo = 1.0 + (speed_percent / 100.0)
    tts_duration: float | None = None
    if config.dubbing_auto_match_audio:
        tts_duration = audio_duration_seconds(tts_path)
        if tts_duration > 0.05 and target_duration > 0.05:
            auto_tempo = tts_duration / target_duration
            auto_min, auto_max = _safe_auto_tempo_bounds(config)
            tempo *= max(auto_min, min(auto_max, auto_tempo))
    tempo = _clamp_natural_tempo(tempo)
    filters.extend(_atempo_filters(tempo))

    reference_volume = mean_volume_db(reference_path) if config.dubbing_auto_match_audio else None
    tts_volume = (
        mean_volume_db(tts_path, sample_rate=_MATCH_OUTPUT_SAMPLE_RATE, channels=_MATCH_OUTPUT_CHANNELS)
        if config.dubbing_auto_match_audio
        else None
    )
    gain: float | None = None
    if reference_volume is not None and tts_volume is not None:
        gain = reference_volume - tts_volume
        gain_min = _finite_float(config.dubbing_volume_gain_min_db, -12.0)
        gain_max = _finite_float(config.dubbing_volume_gain_max_db, 12.0)
        if gain_min > gain_max:
            gain_min, gain_max = gain_max, gain_min
        gain = max(gain_min, min(gain_max, gain))
        if abs(gain) >= 0.5:
            filters.append(_audio_format_filter(_MATCH_OUTPUT_SAMPLE_RATE, _MATCH_OUTPUT_CHANNELS))
            filters.append(f"volume={gain:.2f}dB")
    return AudioMatchPlan(
        filters=tuple(filters),
        tempo=tempo,
        gain_db=gain,
        tts_duration_seconds=tts_duration,
        reference_volume_db=reference_volume,
        tts_volume_db=tts_volume,
    )


def _safe_auto_tempo_bounds(config: AppConfig) -> tuple[float, float]:
    lower = max(_NATURAL_TEMPO_MIN, min(1.0, _finite_float(config.dubbing_speed_min, _NATURAL_TEMPO_MIN)))
    upper = min(_NATURAL_TEMPO_MAX, max(1.0, _finite_float(config.dubbing_speed_max, _NATURAL_TEMPO_MAX)))
    if lower > upper:
        return (_NATURAL_TEMPO_MIN, _NATURAL_TEMPO_MAX)
    return (lower, upper)


def _finite_float(value: object, default: float) -> float:
    return _core_finite_float(value, default=default)


def _clamp_natural_tempo(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    if value <= 0:
        return _NATURAL_TEMPO_MIN
    return max(_NATURAL_TEMPO_MIN, min(_NATURAL_TEMPO_MAX, value))


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
    duration = probe_duration_seconds(path)
    if duration > 0:
        return duration

    fallback_duration = _fallback_audio_duration_seconds(path)
    if fallback_duration > 0:
        _warn_duration_fallback(path, fallback_duration)
        return fallback_duration
    return 0.0


def mean_volume_db(path: Path, *, sample_rate: int | None = None, channels: int | None = None) -> float | None:
    filters: list[str] = []
    if sample_rate is not None or channels is not None:
        filters.append(_audio_format_filter(sample_rate, channels))
    filters.append("volumedetect")
    try:
        completed = run_ffmpeg(
            [
                "-nostats",
                "-i",
                path,
                "-af",
                ",".join(filters),
                "-f",
                "null",
                "-",
            ],
            loglevel=None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", completed.stderr)
        return float(match.group(1)) if match else None
    except Exception:
        return None


def _audio_format_filter(sample_rate: int | None, channels: int | None) -> str:
    args: list[str] = []
    if sample_rate is not None:
        args.append(f"sample_rates={_positive_int(sample_rate, default=_MATCH_OUTPUT_SAMPLE_RATE)}")
    if channels is not None:
        channel_layout = "mono" if _positive_int(channels, default=_MATCH_OUTPUT_CHANNELS) == 1 else "stereo"
        args.append(f"channel_layouts={channel_layout}")
    return f"aformat={':'.join(args)}" if args else "anull"


def _positive_int(value: object, *, default: int) -> int:
    return _core_positive_int(value, default=default)


def _median_pitch_hz(path: Path) -> float:
    return _pitch_stats(path).median_hz


def _fallback_audio_duration_seconds(path: Path) -> float:
    for reader in (_wave_duration_seconds, _soundfile_duration_seconds, _librosa_duration_seconds):
        duration = reader(path)
        if duration > 0:
            return duration
    return 0.0


def _wave_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
        if sample_rate > 0 and frame_count > 0:
            return frame_count / float(sample_rate)
    except Exception:
        return 0.0
    return 0.0


def _soundfile_duration_seconds(path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        if duration > 0:
            return duration
        sample_rate = float(getattr(info, "samplerate", 0.0) or 0.0)
        frames = float(getattr(info, "frames", 0.0) or 0.0)
        if sample_rate > 0 and frames > 0:
            return frames / sample_rate
    except Exception:
        return 0.0
    return 0.0


def _librosa_duration_seconds(path: Path) -> float:
    try:
        import librosa

        try:
            return float(librosa.get_duration(path=str(path)))
        except TypeError:
            samples, sample_rate = librosa.load(str(path), sr=None, mono=False)
            return float(librosa.get_duration(y=samples, sr=sample_rate))
    except Exception:
        return 0.0


def _warn_duration_fallback(path: Path, duration_seconds: float) -> None:
    global _DURATION_FALLBACK_WARNING_EMITTED
    if not _DURATION_FALLBACK_WARNING_EMITTED:
        _LOGGER.warning(
            "ffprobe did not return a duration; using audio fallback duration. "
            "If this repeats, verify ffprobe is installed and not blocked by Windows policy."
        )
        _DURATION_FALLBACK_WARNING_EMITTED = True
    _LOGGER.debug("Audio duration fallback used for %s: %.3fs", path, duration_seconds)


def _pitch_stats(path: Path) -> PitchStats:
    try:
        import librosa
        import numpy as np

        samples, sample_rate = librosa.load(str(path), sr=16000, mono=True)
        if samples.size < sample_rate // 10:
            return PitchStats(0.0, 0.0, 0.0)
        f0 = librosa.yin(samples, fmin=70, fmax=350, sr=sample_rate)
        voiced = f0[np.isfinite(f0)]
        voiced = voiced[(voiced >= 70) & (voiced <= 350)]
        voiced_ratio = float(voiced.size / max(1, f0.size))
        if voiced.size == 0:
            return PitchStats(0.0, 0.0, 0.0)
        median = float(np.median(voiced))
        q25, q75 = np.percentile(voiced, [25, 75])
        return PitchStats(median, float(q75 - q25), voiced_ratio)
    except Exception:
        return PitchStats(0.0, 0.0, 0.0)


def _classify_pitch_gender(stats: PitchStats, duration_seconds: float) -> tuple[str, float]:
    pitch = stats.median_hz
    if pitch <= 0 or stats.voiced_ratio < 0.04:
        return ("unknown", 0.0)
    if 165 <= pitch <= 185:
        return ("unknown", _quality_adjusted_confidence(0.28, stats, duration_seconds))

    if pitch < 165:
        base = 0.55 + min(0.4, (165 - pitch) / 90.0)
        return ("male", _quality_adjusted_confidence(base, stats, duration_seconds))

    base = 0.55 + min(0.4, (pitch - 185) / 90.0)
    return ("female", _quality_adjusted_confidence(base, stats, duration_seconds))


def _quality_adjusted_confidence(base: float, stats: PitchStats, duration_seconds: float) -> float:
    confidence = max(0.0, min(0.98, base))
    if duration_seconds < 0.45:
        confidence *= 0.45
    elif duration_seconds < 0.9:
        confidence *= 0.7
    if stats.voiced_ratio < 0.18:
        confidence *= 0.65
    elif stats.voiced_ratio < 0.35:
        confidence *= 0.82
    if stats.iqr_hz > 95:
        confidence *= 0.7
    elif stats.iqr_hz > 65:
        confidence *= 0.85
    return round(max(0.0, min(0.98, confidence)), 3)


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
