from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ai_player.core.app_logging import get_logger
from ai_player.core.config import PROJECT_ROOT
from ai_player.core.value_utils import positive_int as _core_positive_int

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
FFPLAY = "ffplay"
LOGGER = get_logger(__name__)
_PROBE_DURATION_CACHE_LOCK = threading.Lock()
_PROBE_DURATION_CACHE: dict[tuple[str, int, int], float] = {}


class ProcessCancelled(RuntimeError):
    """Raised when a cancel callback stops an external process."""


def run_ffmpeg(
    args: list[object],
    *,
    check: bool = True,
    loglevel: str | None = "error",
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command: list[str] = [ffmpeg_executable(), "-hide_banner"]
    if loglevel:
        command.extend(["-loglevel", loglevel])
    command.extend(str(arg) for arg in args)
    return subprocess.run(command, check=check, **kwargs)


def run_cancelable_process(
    command: Sequence[object],
    *,
    cancel_callback: Callable[[], bool],
    cancel_strategy: str = "terminate",
    check: bool = True,
    poll_interval_seconds: float = 0.1,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command_text = resolve_media_command(command)
    if cancel_strategy == "quit" and "stdin" not in kwargs:
        kwargs["stdin"] = subprocess.PIPE
    process = subprocess.Popen(command_text, **kwargs)
    try:
        capture_pipe = kwargs.get("stdout") == subprocess.PIPE or kwargs.get("stderr") == subprocess.PIPE
        stdout = None
        stderr = None
        if capture_pipe:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=max(0.01, poll_interval_seconds))
                    return_code = process.returncode
                    break
                except subprocess.TimeoutExpired:
                    if cancel_callback():
                        if cancel_strategy == "quit":
                            _quit_process(process)
                        else:
                            terminate_process(process)
                        raise ProcessCancelled("Process cancelled") from None
        else:
            while True:
                return_code = process.poll()
                if return_code is not None:
                    break
                if cancel_callback():
                    if cancel_strategy == "quit":
                        _quit_process(process)
                    else:
                        terminate_process(process)
                    raise ProcessCancelled("Process cancelled")
                time.sleep(max(0.01, poll_interval_seconds))
        if check and return_code:
            raise subprocess.CalledProcessError(return_code, command_text, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command_text, return_code, stdout, stderr)
    finally:
        _close_process_stdin(process)


def run_ffmpeg_cancelable(
    args: list[object],
    *,
    cancel_callback: Callable[[], bool],
    cancel_strategy: str = "terminate",
    check: bool = True,
    loglevel: str | None = "error",
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command: list[object] = [ffmpeg_executable(), "-hide_banner"]
    if loglevel:
        command.extend(["-loglevel", loglevel])
    command.extend(args)
    return run_cancelable_process(
        command,
        cancel_callback=cancel_callback,
        cancel_strategy=cancel_strategy,
        check=check,
        **kwargs,
    )


def run_ffprobe(
    args: list[object],
    *,
    check: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command = [ffprobe_executable(), *[str(arg) for arg in args]]
    return subprocess.run(command, check=check, **kwargs)


def ffmpeg_executable() -> str:
    return _resolve_media_executable("ffmpeg", "AI_PLAYER_FFMPEG_PATH")


def ffprobe_executable() -> str:
    return _resolve_media_executable("ffprobe", "AI_PLAYER_FFPROBE_PATH")


def ffplay_executable() -> str:
    return _resolve_media_executable("ffplay", "AI_PLAYER_FFPLAY_PATH")


def resolve_media_command(command: Sequence[object]) -> list[str]:
    command_text = [str(arg) for arg in command]
    if not command_text:
        return command_text
    executable = Path(command_text[0]).name.lower()
    if executable in {"ffmpeg", "ffmpeg.exe"}:
        command_text[0] = ffmpeg_executable()
    elif executable in {"ffprobe", "ffprobe.exe"}:
        command_text[0] = ffprobe_executable()
    elif executable in {"ffplay", "ffplay.exe"}:
        command_text[0] = ffplay_executable()
    return command_text


def _resolve_media_executable(name: str, env_var: str) -> str:
    for candidate in _media_executable_candidates(name, env_var):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name


def _media_executable_candidates(name: str, env_var: str) -> list[Path]:
    executable = _executable_name(name)
    candidates: list[Path] = []
    configured = os.getenv(env_var, "").strip()
    if configured:
        candidates.append(Path(configured))

    candidates.extend(
        [
            PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / executable,
            PROJECT_ROOT / "dist" / "ffmpeg" / "bin" / executable,
            PROJECT_ROOT / "models" / "ffmpeg" / "bin" / executable,
        ]
    )

    if os.name == "nt":
        chocolatey_root = Path(os.getenv("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
        candidates.append(chocolatey_root / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / executable)

    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    return candidates


def _executable_name(name: str) -> str:
    if os.name == "nt" and Path(name).suffix.lower() != ".exe":
        return f"{name}.exe"
    if sys.platform == "win32" and Path(name).suffix.lower() != ".exe":
        return f"{name}.exe"
    return name


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
    sample_rate_value = _positive_int(sample_rate, default=44100)
    channels_value = _positive_int(channels, default=2)
    channel_layout = "mono" if channels_value == 1 else "stereo"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={channel_layout}:sample_rate={sample_rate_value}",
            "-t",
            f"{_seconds_value(duration_seconds, default=0.0):.3f}",
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
    sample_rate_value = _positive_int(sample_rate, default=44100)
    channels_value = _positive_int(channels, default=2)
    run_ffmpeg(
        [
            "-i",
            input_path,
            "-ar",
            sample_rate_value,
            "-ac",
            channels_value,
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
    start = _seconds_value(start_seconds, default=0.0)
    duration = max(0.05, _seconds_value(duration_seconds, default=0.05))
    sample_rate_value = _positive_int(sample_rate, default=16000)
    channels_value = _positive_int(channels, default=1)
    args = [
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        source_path,
        "-vn",
        "-ac",
        channels_value,
        "-ar",
        sample_rate_value,
        "-y",
        output_path,
    ]
    if cancel_callback is None:
        run_ffmpeg(args)
    else:
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback)


def probe_duration_seconds(path: Path) -> float:
    cache_key = _probe_duration_cache_key(path)
    if cache_key is not None:
        with _PROBE_DURATION_CACHE_LOCK:
            cached = _PROBE_DURATION_CACHE.get(cache_key)
            if cached is not None:
                return cached

    duration = 0.0
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
                duration = value
                break
        if duration > 0:
            break

    if cache_key is not None:
        with _PROBE_DURATION_CACHE_LOCK:
            _PROBE_DURATION_CACHE[cache_key] = duration
    return duration


def clear_probe_duration_cache() -> None:
    with _PROBE_DURATION_CACHE_LOCK:
        _PROBE_DURATION_CACHE.clear()


def safe_float(value: object) -> float | None:
    try:
        text = str(value or "").strip()
        if not text or text.upper() == "N/A":
            return None
        parsed = float(text)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _seconds_value(value: object, *, default: float) -> float:
    parsed = safe_float(value)
    return default if parsed is None else parsed


def _positive_int(value: object, *, default: int) -> int:
    return _core_positive_int(value, default=default)


def _probe_duration_cache_key(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
        resolved = path.resolve()
    except OSError:
        return None
    return (str(resolved), int(stat.st_mtime_ns), int(stat.st_size))


def terminate_process(process: subprocess.Popen, timeout_seconds: float = 2.0) -> None:
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
            LOGGER.warning("Failed to wait for killed process after terminate timeout.", exc_info=True)
    except Exception:
        LOGGER.warning("Failed to terminate process; trying kill.", exc_info=True)
        try:
            process.kill()
        except Exception:
            LOGGER.warning("Failed to kill process after terminate failure.", exc_info=True)


_terminate_process = terminate_process


def _quit_process(process: subprocess.Popen, timeout_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    try:
        if process.stdin is not None:
            process.stdin.write(b"q\n")
            process.stdin.flush()
        process.wait(timeout=timeout_seconds)
    except Exception:
        LOGGER.warning("Failed to quit process cleanly; falling back to terminate.", exc_info=True)
        terminate_process(process)


def _close_process_stdin(process: subprocess.Popen) -> None:
    try:
        stdin = process.stdin
        if stdin is not None and not stdin.closed:
            stdin.close()
    except Exception:
        LOGGER.warning("Failed to close process stdin.", exc_info=True)
