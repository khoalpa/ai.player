from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_player.services.demucs_separation import DemucsSeparationError, demucs_available, demucs_executable
from ai_player.services.ffmpeg import resolve_media_command

ProcessRunner = Callable[[list[str]], None]

SOURCE_VOICE_FILTER_MODES = {"auto", "fast", "ai"}
SOURCE_VOICE_FILTER_DEFAULT_MODE = "auto"
SOURCE_VOICE_FILTER_DEMUCS_MODEL = "htdemucs"


class SourceVoiceFilterError(RuntimeError):
    pass


class SourceVoiceFilterCancelled(SourceVoiceFilterError):
    pass


@dataclass(frozen=True)
class SourceVoiceFilterResult:
    output_path: Path
    backend: str
    mode: str = SOURCE_VOICE_FILTER_DEFAULT_MODE
    warning: str = ""


def normalize_source_voice_filter_mode(mode: str) -> str:
    value = str(mode or "").strip().lower().replace("-", "_")
    aliases = {
        "": SOURCE_VOICE_FILTER_DEFAULT_MODE,
        "default": SOURCE_VOICE_FILTER_DEFAULT_MODE,
        "center": "fast",
        "ffmpeg": "fast",
        "quick": "fast",
        "demucs": "ai",
        "model": "ai",
        "high_quality": "ai",
    }
    value = aliases.get(value, value)
    return value if value in SOURCE_VOICE_FILTER_MODES else SOURCE_VOICE_FILTER_DEFAULT_MODE


def source_voice_filter_signature(mode: str, backend: str | None = None) -> str:
    normalized = normalize_source_voice_filter_mode(mode)
    actual_backend = normalize_source_voice_filter_mode(backend) if backend else ""
    if normalized == "auto" and actual_backend == "ai":
        return f"auto-ai-{SOURCE_VOICE_FILTER_DEMUCS_MODEL}-h264-720p-v1"
    if normalized == "auto" and actual_backend == "fast":
        return "auto-fast-ffmpeg-center-h264-720p-v4"
    if actual_backend in {"ai", "fast"}:
        normalized = actual_backend
    if normalized == "ai":
        return f"ai-{SOURCE_VOICE_FILTER_DEMUCS_MODEL}-h264-720p-v1"
    if normalized == "fast":
        return "fast-ffmpeg-center-h264-720p-v4"
    if demucs_available():
        return f"auto-ai-{SOURCE_VOICE_FILTER_DEMUCS_MODEL}-h264-720p-v1"
    return "auto-fast-ffmpeg-center-h264-720p-v4"


def source_voice_filter_cached_output_valid(output_path: Path, mode: str) -> bool:
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return False
    metadata = read_source_voice_filter_metadata(output_path)
    backend = str(metadata.get("backend") or "").strip().lower()
    if backend not in {"fast", "ai"}:
        backend = None
    normalized_mode = normalize_source_voice_filter_mode(mode)
    if backend is None:
        return normalized_mode != "auto" or not demucs_available()
    if normalized_mode == "fast":
        return backend == "fast"
    if normalized_mode == "ai":
        return backend == "ai"
    if backend == "ai":
        return True
    cached_mode = normalize_source_voice_filter_mode(metadata.get("mode")) if "mode" in metadata else ""
    return backend == "fast" and (cached_mode == "auto" or not demucs_available())


def read_source_voice_filter_metadata(output_path: Path) -> dict[str, object]:
    try:
        metadata = json.loads(_metadata_path(output_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def read_source_voice_filter_backend(output_path: Path) -> str | None:
    metadata = read_source_voice_filter_metadata(output_path)
    backend = str(metadata.get("backend") or "").strip().lower() if isinstance(metadata, dict) else ""
    return backend if backend in {"fast", "ai"} else None


def write_source_voice_filter_metadata(result: SourceVoiceFilterResult) -> None:
    metadata = {
        "backend": result.backend,
        "mode": normalize_source_voice_filter_mode(result.mode),
    }
    if result.warning:
        metadata["warning"] = result.warning
    _metadata_path(result.output_path).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def apply_source_voice_filter(
    source_path: Path,
    output_path: Path,
    *,
    mode: str = SOURCE_VOICE_FILTER_DEFAULT_MODE,
    process_runner: ProcessRunner | None = None,
) -> SourceVoiceFilterResult:
    normalized_mode = normalize_source_voice_filter_mode(mode)
    runner = process_runner or _run_process
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if normalized_mode == "fast":
        _create_fast_filtered_video(source_path, output_path, runner)
        return SourceVoiceFilterResult(output_path=output_path, backend="fast", mode=normalized_mode)

    if normalized_mode == "ai":
        _create_demucs_filtered_video(source_path, output_path, runner)
        return SourceVoiceFilterResult(output_path=output_path, backend="ai", mode=normalized_mode)

    warning = ""
    if demucs_available():
        try:
            _create_demucs_filtered_video(source_path, output_path, runner)
            return SourceVoiceFilterResult(output_path=output_path, backend="ai", mode=normalized_mode)
        except SourceVoiceFilterCancelled:
            raise
        except Exception as exc:
            _remove_partial_output(output_path)
            warning = f"AI voice separation failed; using fast filter instead: {_exception_summary(exc)}"

    _create_fast_filtered_video(source_path, output_path, runner)
    return SourceVoiceFilterResult(output_path=output_path, backend="fast", mode=normalized_mode, warning=warning)


def _create_fast_filtered_video(source_path: Path, output_path: Path, runner: ProcessRunner) -> None:
    audio_filter = (
        "aformat=channel_layouts=stereo,"
        "pan=stereo|c0=0.70*c0-0.55*c1|c1=0.70*c1-0.55*c0,"
        "volume=1.4,alimiter=limit=0.95"
    )
    runner(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-map",
            "0:v?",
            "-map",
            "0:a:0",
            *_h264_playback_args(),
            "-af",
            audio_filter,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
    )


def _create_demucs_filtered_video(source_path: Path, output_path: Path, runner: ProcessRunner) -> None:
    if not demucs_available():
        raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")

    with tempfile.TemporaryDirectory(prefix=f"{output_path.stem}-demucs-", dir=str(output_path.parent)) as temp_name:
        temp_dir = Path(temp_name)
        runner(
            [
                "demucs",
                "-n",
                SOURCE_VOICE_FILTER_DEMUCS_MODEL,
                "--two-stems",
                "vocals",
                "-o",
                str(temp_dir),
                str(source_path),
            ]
        )
        no_vocals = temp_dir / SOURCE_VOICE_FILTER_DEMUCS_MODEL / source_path.stem / "no_vocals.wav"
        if not no_vocals.exists():
            raise DemucsSeparationError(f"Demucs did not create expected file: {no_vocals}")
        runner(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-i",
                str(no_vocals),
                "-map",
                "0:v?",
                "-map",
                "1:a:0",
                *_h264_playback_args(),
                "-af",
                "aformat=channel_layouts=stereo,alimiter=limit=0.95",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-y",
                str(output_path),
            ]
        )


def _h264_playback_args() -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-profile:v",
        "main",
        "-level:v",
        "4.0",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=-2:min(720\\,ih)",
    ]


def _run_process(command: list[str]) -> None:
    executable = command[0]
    resolved_command = resolve_media_command(command)
    if executable == "demucs":
        resolved_command[0] = demucs_executable()
    if shutil.which(resolved_command[0]) is None and not Path(resolved_command[0]).is_file():
        raise SourceVoiceFilterError(f"Missing executable: {executable}")
    subprocess.run(resolved_command, check=True)


def _remove_partial_output(output_path: Path) -> None:
    try:
        if output_path.exists():
            output_path.unlink()
    except OSError:
        pass


def _exception_summary(exc: Exception, max_length: int = 240) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    message = " ".join(message.split())
    if len(message) > max_length:
        return f"{message[: max_length - 3]}..."
    return message


def _metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(f"{output_path.suffix}.json")
