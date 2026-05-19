from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
FFPLAY = "ffplay"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    check: bool = True,
    poll_interval_seconds: float = 0.1,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    command_text = resolve_media_command(command)
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
    command: list[object] = [ffmpeg_executable(), "-hide_banner"]
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
