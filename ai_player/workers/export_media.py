from __future__ import annotations

from pathlib import Path

from ai_player.pipeline.export_plan import (
    ExportRange,
    VideoQualitySettings,
    document_scale_filter,
    format_seconds_arg,
    scale_filter,
)
from ai_player.services.ffmpeg import concat_file_line
from ai_player.workers.worker_values import duration_value, positive_int


def silence_args(duration_seconds: float, output_path: Path) -> list[object]:
    duration = _duration_value(duration_seconds, default=0.0)
    return [
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{duration:.3f}",
        "-c:a",
        "pcm_s16le",
        "-y",
        output_path,
    ]


def to_wav_args(input_path: Path, output_path: Path, *, sample_rate: int = 44100, channels: int = 2) -> list[object]:
    return [
        "-i",
        input_path,
        *_pcm_wav_output_args(output_path, sample_rate=sample_rate, channels=channels),
    ]


def trim_leading_silence_args(audio_path: Path, trimmed_path: Path) -> list[object]:
    return [
        "-i",
        audio_path,
        "-af",
        "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB",
        "-y",
        trimmed_path,
    ]


def extract_source_audio_args(video_path: str, output_path: Path, export_range: ExportRange) -> list[object]:
    command: list[object] = _range_input_args(video_path, export_range)
    command.extend(["-vn", "-ac", "1", "-ar", "16000", "-y", str(output_path)])
    return command


def full_quality_audio_args(video_path: str, output_path: Path, export_range: ExportRange) -> list[object]:
    command: list[object] = _range_input_args(video_path, export_range)
    command.extend(
        [
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(output_path),
        ]
    )
    return command


def fast_background_stem_args(source_audio: Path, background_path: Path) -> list[object]:
    return [
        "-i",
        source_audio,
        "-af",
        "aformat=channel_layouts=stereo,"
        "pan=stereo|c0=0.70*c0-0.55*c1|c1=0.70*c1-0.55*c0,"
        "volume=1.4,alimiter=limit=0.95",
        *_pcm_wav_output_args(background_path, sample_rate=48000, channels=2),
    ]


def fast_voice_stem_args(source_audio: Path, voice_path: Path) -> list[object]:
    return [
        "-i",
        source_audio,
        "-af",
        "aformat=channel_layouts=stereo,"
        "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1,"
        "alimiter=limit=0.95",
        *_pcm_wav_output_args(voice_path, sample_rate=48000, channels=2),
    ]


def mux_video_args(
    *,
    video_path: str,
    dubbed_audio: Path,
    target_path: Path,
    export_range: ExportRange,
    quality: VideoQualitySettings,
    duration_seconds: float | None = None,
) -> list[object]:
    command: list[object] = []
    if export_range.start_seconds > 0.0:
        command.extend(["-ss", format_seconds_arg(export_range.start_seconds)])
    command.extend(["-i", video_path, "-i", str(dubbed_audio)])
    mux_duration = duration_seconds if duration_seconds is not None else export_range.duration_seconds
    if mux_duration is not None:
        command.extend(["-t", format_seconds_arg(mux_duration)])
    command.extend(["-map", "0:v:0", "-map", "1:a:0"])
    if quality.copy_source_video:
        command.extend(["-c:v", "copy"])
    else:
        command.extend(
            [
                "-vf",
                scale_filter(quality.width, quality.height),
                "-c:v",
                "libx264",
                "-preset",
                quality.preset,
                "-crf",
                str(quality.crf),
            ]
        )
    command.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            quality.audio_bitrate,
            "-movflags",
            "+faststart",
            "-shortest",
            "-y",
            str(target_path),
        ]
    )
    return command


def document_video_concat_lines(
    pages: list[object],
    image_paths: list[Path],
    audio_duration_seconds: float,
) -> str:
    total_page_duration = sum(
        _duration_value(getattr(page, "duration_seconds", 0.5), default=0.5, minimum=0.5) for page in pages
    )
    extra_duration = max(0.0, _duration_value(audio_duration_seconds, default=0.0) - total_page_duration)
    lines: list[str] = []
    for index, (page, image_path) in enumerate(zip(pages, image_paths, strict=True)):
        duration = _duration_value(getattr(page, "duration_seconds", 0.5), default=0.5, minimum=0.5)
        if index == len(pages) - 1:
            duration += extra_duration
        lines.append(concat_file_line(image_path))
        lines.append(f"duration {duration:.3f}\n")
    if image_paths:
        lines.append(concat_file_line(image_paths[-1]))
    return "".join(lines)


def document_video_args(concat_file: Path, output_path: Path, quality: VideoQualitySettings) -> list[object]:
    return [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-vf",
        document_scale_filter(quality.width, quality.height),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        quality.preset,
        "-crf",
        str(quality.crf),
        "-y",
        str(output_path),
    ]


def mux_document_video_args(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    quality: VideoQualitySettings,
) -> list[object]:
    return [
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        quality.audio_bitrate,
        "-movflags",
        "+faststart",
        "-y",
        str(output_path),
    ]


def _duration_value(value: object, *, default: float, minimum: float = 0.0) -> float:
    return duration_value(value, default=default, minimum=minimum)


def _positive_int(value: object, *, default: int) -> int:
    return positive_int(value, default=default)


def _range_input_args(video_path: str, export_range: ExportRange) -> list[object]:
    command: list[object] = []
    if export_range.start_seconds > 0.0:
        command.extend(["-ss", format_seconds_arg(export_range.start_seconds)])
    command.extend(["-i", video_path])
    if export_range.duration_seconds is not None:
        command.extend(["-t", format_seconds_arg(export_range.duration_seconds)])
    return command


def _pcm_wav_output_args(output_path: Path, *, sample_rate: int = 44100, channels: int = 2) -> list[object]:
    return [
        "-ar",
        _positive_int(sample_rate, default=44100),
        "-ac",
        _positive_int(channels, default=2),
        "-c:a",
        "pcm_s16le",
        "-y",
        output_path,
    ]
