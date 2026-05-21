from __future__ import annotations

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
        start = max(0.0, float(self.start_seconds or 0.0))
        end = None if self.end_seconds is None else max(start, float(self.end_seconds))
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
        cue_start = max(0.0, float(start_seconds))
        cue_end = max(cue_start, float(end_seconds))
        range_end = self.end_seconds
        if range_end is not None and cue_start >= range_end:
            return False
        return cue_end > self.start_seconds

    def shift(self, start_seconds: float) -> float:
        return max(0.0, float(start_seconds) - self.start_seconds)


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
    return (
        f"scale=w=min({int(width)}\\,iw):h=min({int(height)}\\,ih):"
        "force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
    )


def document_scale_filter(width: int, height: int) -> str:
    width = int(width)
    height = int(height)
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
        cue_text = " ".join(lines[1:]).strip()
        if not cue_text:
            continue
        cues.append(TranscriptCue(parse_srt_time(start_raw), parse_srt_time(end_raw), cue_text))
    return cues


def parse_srt_time(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)(?:[,.](\d+))?", value.strip())
    if not match:
        return 0.0
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int((millis or "0").ljust(3, "0")[:3]) / 1000.0


def format_seconds_arg(value: float) -> str:
    return f"{max(0.0, float(value)):.3f}"


def cues_end_seconds(cues: list[ExportCue]) -> float:
    if not cues:
        return 0.0
    return max(cue.start_seconds + max(0.0, cue.duration_seconds or 0.0) for cue in cues)


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
    channel_layout = "mono" if int(channels) == 1 else "stereo"
    for index, (path, start_seconds) in enumerate(audio_inputs):
        args.extend(["-i", path])
        delay_ms = max(0, int(round(float(start_seconds or 0.0) * 1000)))
        label = f"a{index}"
        filter_parts.append(
            f"[{index}:a]aformat=sample_rates={int(sample_rate)}:channel_layouts={channel_layout},"
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
            str(int(sample_rate)),
            "-ac",
            str(int(channels)),
            "-y",
            output_path,
        ]
    )
    return args
