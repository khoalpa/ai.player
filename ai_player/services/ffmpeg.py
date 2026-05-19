from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


class ProcessCancelled(RuntimeError):
    """Raised when a cancel callback stops an external process."""


def run_ffmpeg(
    args: list[object],
    *,
    check: bool = True,
    loglevel: str | None = "error",
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command: list[str] = [FFMPEG, "-hide_banner"]
    if loglevel:
        command.extend(["-loglevel", loglevel])
    command.extend(str(arg) for arg in args)
    return subprocess.run(command, check=check, **kwargs)


def run_cancelable_process(
    command: Sequence[object],
    *,
    cancel_callback: Callable[[], bool],
    check: bool = True,
    poll_interval_seconds: float = 0.1,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command_text = [str(arg) for arg in command]
    process = subprocess.Popen(command_text, **kwargs)
    while True:
        return_code = process.poll()
        if return_code is not None:
            break
        if cancel_callback():
            _terminate_process(process)
            raise ProcessCancelled("Process cancelled")
        time.sleep(max(0.01, poll_interval_seconds))
    if check and return_code:
        raise subprocess.CalledProcessError(return_code, command_text)
    return subprocess.CompletedProcess(command_text, return_code)


def run_ffmpeg_cancelable(
    args: list[object],
    *,
    cancel_callback: Callable[[], bool],
    check: bool = True,
    loglevel: str | None = "error",
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command: list[object] = [FFMPEG, "-hide_banner"]
    if loglevel:
        command.extend(["-loglevel", loglevel])
    command.extend(args)
    return run_cancelable_process(command, cancel_callback=cancel_callback, check=check, **kwargs)


def run_ffprobe(
    args: list[object],
    *,
    check: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command = [FFPROBE, *[str(arg) for arg in args]]
    return subprocess.run(command, check=check, **kwargs)


def concat_escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "'\\''")


def concat_file_line(path: Path) -> str:
    return f"file '{concat_escape(path)}'\n"


def make_silence(
    duration_seconds: float,
    output_path: Path,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
) -> None:
    channel_layout = "mono" if channels == 1 else "stereo"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={channel_layout}:sample_rate={int(sample_rate)}",
            "-t",
            f"{max(0.0, duration_seconds):.3f}",
            "-c:a",
            "pcm_s16le",
            "-y",
            output_path,
        ]
    )


def to_wav(
    input_path: Path,
    output_path: Path,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
) -> None:
    run_ffmpeg(
        [
            "-i",
            input_path,
            "-ar",
            int(sample_rate),
            "-ac",
            int(channels),
            "-c:a",
            "pcm_s16le",
            "-y",
            output_path,
        ]
    )


def trim_leading_silence(audio_path: Path) -> Path:
    trimmed_path = audio_path.with_name(f"{audio_path.stem}-trimmed{audio_path.suffix}")
    run_ffmpeg(
        [
            "-i",
            audio_path,
            "-af",
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB",
            "-y",
            trimmed_path,
        ],
        check=False,
    )
    if trimmed_path.exists() and trimmed_path.stat().st_size > 0:
        return trimmed_path
    return audio_path


def extract_audio_range(
    source_path: Path,
    start_seconds: float,
    duration_seconds: float,
    output_path: Path,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    cancel_callback: Callable[[], bool] | None = None,
) -> None:
    args = [
        "-ss",
        f"{max(0.0, start_seconds):.3f}",
        "-t",
        f"{max(0.05, duration_seconds):.3f}",
        "-i",
        source_path,
        "-vn",
        "-ac",
        int(channels),
        "-ar",
        int(sample_rate),
        "-y",
        output_path,
    ]
    if cancel_callback is None:
        run_ffmpeg(args)
    else:
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback)


def probe_duration_seconds(path: Path) -> float:
    for entry in ("format=duration", "stream=duration"):
        try:
            completed = run_ffprobe(
                [
                    "-v",
                    "error",
                    "-show_entries",
                    entry,
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            continue
        for line in completed.stdout.splitlines():
            value = safe_float(line)
            if value is not None and value > 0:
                return value
    return 0.0


def safe_float(value: object) -> float | None:
    try:
        text = str(value or "").strip()
        if not text or text.upper() == "N/A":
            return None
        parsed = float(text)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _terminate_process(process: subprocess.Popen, timeout_seconds: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=timeout_seconds)
        except Exception:
            pass
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
