from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExportCue:
    start_seconds: float
    original: str
    translated: str
    audio_path: Path
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class TranscriptCue:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoQualitySettings:
    crf: int
    preset: str
    width: int
    height: int
    audio_bitrate: str
    copy_source_video: bool = False


@dataclass(frozen=True)
class ExportRange:
    start_seconds: float = 0.0
    end_seconds: float | None = None

    def __post_init__(self) -> None:
        start = _finite_seconds(self.start_seconds, default=0.0) or 0.0
        end_value = _finite_seconds(self.end_seconds, default=None)
        end = None if end_value is None else max(start, end_value)
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)

    @property
    def active(self) -> bool:
        return self.start_seconds > 0.0 or self.end_seconds is not None

    @property
    def duration_seconds(self) -> float | None:
        if self.end_seconds is None:
            return None
        return max(0.0, self.end_seconds - self.start_seconds)

    def overlaps(self, start_seconds: float, end_seconds: float) -> bool:
        cue_start = _finite_seconds(start_seconds, default=0.0) or 0.0
        cue_end = max(cue_start, _finite_seconds(end_seconds, default=cue_start) or cue_start)
        range_end = self.end_seconds
        if range_end is not None and cue_start >= range_end:
            return False
        return cue_end > self.start_seconds

    def shift(self, start_seconds: float) -> float:
        return max(0.0, (_finite_seconds(start_seconds, default=0.0) or 0.0) - self.start_seconds)


def video_quality_settings(value: str) -> VideoQualitySettings:
    quality = str(value or "source").strip().lower()
    if quality == "compact":
        return VideoQualitySettings(crf=28, preset="veryfast", width=1280, height=720, audio_bitrate="160k")
    if quality == "balanced":
        return VideoQualitySettings(crf=23, preset="medium", width=1920, height=1080, audio_bitrate="192k")
    if quality == "high":
        return VideoQualitySettings(crf=18, preset="slow", width=1920, height=1080, audio_bitrate="256k")
    if quality == "archival":
        return VideoQualitySettings(crf=16, preset="slow", width=3840, height=2160, audio_bitrate="320k")
    return VideoQualitySettings(
        crf=18,
        preset="slow",
        width=1920,
        height=1080,
        audio_bitrate="256k",
        copy_source_video=False,
    )


def scale_filter(width: int, height: int) -> str:
    width = _positive_int(width, default=1920)
    height = _positive_int(height, default=1080)
    return (
        f"scale=w=min({width}\\,iw):h=min({height}\\,ih):"
        "force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
    )


def document_scale_filter(width: int, height: int) -> str:
    width = _positive_int(width, default=1920)
    height = _positive_int(height, default=1080)
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p"
    )


def read_srt_cues(path: Path) -> list[TranscriptCue]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    cues: list[TranscriptCue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) >= 2 and lines[0].isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        start_seconds = parse_srt_time(start_raw)
        end_seconds = max(start_seconds + 0.25, parse_srt_time(end_raw))
        cue_text = _clean_text(" ".join(lines[1:]))
        if not cue_text:
            continue
        cues.append(TranscriptCue(start_seconds, end_seconds, cue_text))
    return cues


def write_srt_cues(path: Path, cues: list[TranscriptCue]) -> None:
    lines: list[str] = []
    index = 1
    for cue in cues:
        start_seconds = _finite_seconds(cue.start_seconds, default=0.0) or 0.0
        end_seconds = max(start_seconds + 0.25, _finite_seconds(cue.end_seconds, default=start_seconds + 0.25) or 0.0)
        start = format_srt_time(start_seconds)
        end = format_srt_time(end_seconds)
        text = _clean_text(cue.text)
        if not text:
            continue
        lines.extend([str(index), f"{start} --> {end}", text, ""])
        index += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_srt_time(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)(?:[,.](\d+))?", value.strip())
    if not match:
        return 0.0
    hours, minutes, seconds, millis = match.groups()
    try:
        parsed = (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int((millis or "0").ljust(3, "0")[:3]) / 1000.0
        )
    except (ValueError, OverflowError):
        return 0.0
    return _finite_seconds(parsed, default=0.0) or 0.0


def format_srt_time(value: float) -> str:
    millis_total = max(0, int(round((_finite_seconds(value, default=0.0) or 0.0) * 1000)))
    seconds_total, millis = divmod(millis_total, 1000)
    minutes_total, seconds = divmod(seconds_total, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_seconds_arg(value: float) -> str:
    return f"{_finite_seconds(value, default=0.0) or 0.0:.3f}"


def _finite_seconds(value: object, *, default: float | None) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(seconds):
        return default
    return max(0.0, seconds)


def _clean_text(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    return " ".join(text.split())


def cues_end_seconds(cues: list[ExportCue]) -> float:
    if not cues:
        return 0.0
    return max(
        (_finite_seconds(cue.start_seconds, default=0.0) or 0.0)
        + (_finite_seconds(cue.duration_seconds, default=0.0) or 0.0)
        for cue in cues
    )


def timeline_mix_args(
    audio_inputs: list[tuple[Path, float]],
    output_path: Path,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
) -> list[object]:
    args: list[object] = []
    filter_parts: list[str] = []
    labels: list[str] = []
    sample_rate = _positive_int(sample_rate, default=44100)
    channels = _audio_channels(channels)
    channel_layout = "mono" if channels == 1 else "stereo"
    for index, (path, start_seconds) in enumerate(audio_inputs):
        args.extend(["-i", path])
        delay_ms = max(0, int(round((_finite_seconds(start_seconds, default=0.0) or 0.0) * 1000)))
        label = f"a{index}"
        filter_parts.append(
            f"[{index}:a]aformat=sample_rates={sample_rate}:channel_layouts={channel_layout},"
            f"adelay={delay_ms}:all=1[{label}]"
        )
        labels.append(f"[{label}]")

    filter_parts.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.98[mix]"
    )
    args.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[mix]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-y",
            output_path,
        ]
    )
    return args


def staged_background_voice_mix_args(
    background_path: Path,
    voice_path: Path,
    output_path: Path,
    *,
    sample_rate: int = 48000,
    channels: int = 2,
    voice_volume_percent: int = 100,
) -> list[object]:
    sample_rate = _positive_int(sample_rate, default=48000)
    channels = _audio_channels(channels)
    channel_layout = "mono" if channels == 1 else "stereo"
    voice_volume_percent = _finite_seconds(voice_volume_percent, default=100.0) or 0.0
    voice_volume = max(0.0, min(2.0, voice_volume_percent / 100.0))
    filter_complex = (
        f"[0:a]aformat=sample_rates={sample_rate}:channel_layouts={channel_layout}[bg];"
        f"[1:a]aformat=sample_rates={sample_rate}:channel_layouts={channel_layout},"
        f"volume={voice_volume:.3f}[voice];"
        "[bg][voice]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=250[ducked];"
        "[ducked][voice]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.98,loudnorm=I=-16:TP=-1.5:LRA=11[mix]"
    )
    return [
        "-i",
        background_path,
        "-i",
        voice_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[mix]",
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-y",
        output_path,
    ]


def _positive_int(value: object, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number > 0 else default


def _audio_channels(value: object) -> int:
    return 1 if _positive_int(value, default=2) == 1 else 2
