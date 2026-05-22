from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.config import AppConfig
from ai_player.services.document_reader import create_document_transcript
from ai_player.services.ffmpeg import ffmpeg_executable
from ai_player.services.runtime_warmup import RuntimeWarmupCancelled, warm_runtime_components
from ai_player.services.source_voice_filter import (
    SourceVoiceFilterCancelled,
    apply_source_voice_filter,
    read_source_voice_filter_backend,
    resolve_source_voice_filter_command,
    source_voice_filter_cached_output_valid,
    write_source_voice_filter_metadata,
)
from ai_player.services.video_source import resolve_video_source


class RuntimeWarmupWorker(QThread):
    status_changed = Signal(str)
    finished_successfully = Signal(object)
    failed = Signal(str)

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            timings = warm_runtime_components(
                self._config,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                progress_callback=self.status_changed.emit,
            )
        except RuntimeWarmupCancelled:
            return
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if not self._stop_requested and not self.isInterruptionRequested():
            self.finished_successfully.emit(timings)


class VideoSourceWorker(QThread):
    resolved = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(object)

    def __init__(
        self,
        url: str,
        playback_quality: str,
        full_cache: bool = True,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._playback_quality = playback_quality
        self._full_cache = full_cache
        self._language_id = language_id
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            self.resolved.emit(
                resolve_video_source(
                    self._url,
                    self._playback_quality,
                    full_cache=self._full_cache,
                    progress_callback=self.progress_changed.emit if self._full_cache else None,
                    cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                    language_id=self._language_id,
                )
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class DocumentTranscriptWorker(QThread):
    ready = Signal(object, bool)
    failed = Signal(str)

    def __init__(
        self,
        path: str,
        start_dubbing: bool,
        seconds_per_segment: int = 6,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._start_dubbing = start_dubbing
        self._seconds_per_segment = seconds_per_segment
        self._language_id = language_id
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            transcript = create_document_transcript(
                self._path,
                seconds_per_segment=self._seconds_per_segment,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                language_id=self._language_id,
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if self._stop_requested or self.isInterruptionRequested():
            return
        self.ready.emit(transcript, self._start_dubbing)


class SourceAudioFilterWorker(QThread):
    ready = Signal(str, str, str)
    failed = Signal(str, str)
    warning = Signal(str, str)

    def __init__(
        self,
        source_path: str,
        output_path: Path,
        mode: str = "auto",
        model: str = "htdemucs",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source_path = source_path
        self._output_path = output_path
        self._mode = mode
        self._model = model
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            _terminate_process(self._process)

    def run(self) -> None:
        try:
            if source_voice_filter_cached_output_valid(self._output_path, self._mode, self._model):
                backend = read_source_voice_filter_backend(self._output_path) or self._mode
                self.ready.emit(self._source_path, str(self._output_path), backend)
                return
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            result = apply_source_voice_filter(
                Path(self._source_path),
                self._output_path,
                mode=self._mode,
                model=self._model,
                process_runner=self._run_process,
            )
            write_source_voice_filter_metadata(result)
            if self._stop_requested:
                return
            if result.warning:
                self.warning.emit(self._source_path, result.warning)
            self.ready.emit(self._source_path, str(self._output_path), result.backend)
        except Exception as exc:
            if not self._stop_requested:
                self.failed.emit(self._source_path, _format_process_exception(exc))
        finally:
            self._process = None

    def _run_process(self, command: list[str]) -> None:
        if self._stop_requested:
            raise SourceVoiceFilterCancelled("Voice filter stopped.")
        resolved_command = resolve_source_voice_filter_command(command)
        self._process = subprocess.Popen(
            resolved_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = self._process.communicate()
        return_code = self._process.returncode
        if self._stop_requested:
            raise SourceVoiceFilterCancelled("Voice filter stopped.")
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, resolved_command, output=stdout, stderr=stderr)


class PlaybackCompatibilityWorker(QThread):
    ready = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, source_path: str, output_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._source_path = source_path
        self._output_path = output_path
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            _terminate_process(self._process)

    def run(self) -> None:
        try:
            if self._output_path.exists() and self._output_path.stat().st_size > 0:
                self.ready.emit(self._source_path, str(self._output_path))
                return
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                self._source_path,
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-profile:v",
                "main",
                "-level:v",
                "4.0",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=-2:min(720\\,ih)",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-movflags",
                "+faststart",
                "-y",
                str(self._output_path),
            ]
            self._process = subprocess.Popen(command)
            return_code = self._process.wait()
            if self._stop_requested:
                return
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
            self.ready.emit(self._source_path, str(self._output_path))
        except Exception as exc:
            if not self._stop_requested:
                self.failed.emit(self._source_path, str(exc))
        finally:
            self._process = None


def _terminate_process(process: subprocess.Popen, timeout_seconds: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _format_process_exception(exc: Exception, max_length: int = 500) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        executable = _process_executable_name(exc.cmd)
        prefix = f"{executable} failed with exit code {exc.returncode}"
        detail = _compact_process_detail(exc.stderr or exc.output or "", max_length=max_length - len(prefix) - 2)
        if detail:
            message = f"{prefix}: {detail}"
        else:
            message = prefix
    else:
        message = str(exc).strip() or exc.__class__.__name__
        message = " ".join(message.split())
    if len(message) > max_length:
        return f"{message[: max_length - 3]}..."
    return message


def _compact_process_detail(detail: object, *, max_length: int = 500) -> str:
    text = str(detail or "").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    message = " ".join(lines)
    if len(message) <= max_length:
        return message
    tail_budget = max(80, max_length - 20)
    return f"...{message[-tail_budget:]}"


def _process_executable_name(command: object) -> str:
    if isinstance(command, (list, tuple)) and command:
        command_parts = [str(part) for part in command]
        if "ai_player.services.demucs_runner" in command_parts:
            return "demucs"
        return str(command[0])
    return str(command or "process")
