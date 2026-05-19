from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.services.document_reader import create_document_transcript
from ai_player.services.video_source import resolve_video_source


class VideoSourceWorker(QThread):
    resolved = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(object)

    def __init__(self, url: str, playback_quality: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._playback_quality = playback_quality
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
                    progress_callback=self.progress_changed.emit,
                    cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                )
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class DocumentTranscriptWorker(QThread):
    ready = Signal(object, bool)
    failed = Signal(str)

    def __init__(self, path: str, start_dubbing: bool, seconds_per_segment: int = 6, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._start_dubbing = start_dubbing
        self._seconds_per_segment = seconds_per_segment
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
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if self._stop_requested or self.isInterruptionRequested():
            return
        self.ready.emit(transcript, self._start_dubbing)


class SourceAudioFilterWorker(QThread):
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
            audio_filter = (
                "aformat=channel_layouts=stereo,"
                "pan=stereo|c0=0.70*c0-0.55*c1|c1=0.70*c1-0.55*c0,"
                "volume=1.4,alimiter=limit=0.95"
            )
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                self._source_path,
                "-map",
                "0:v?",
                "-map",
                "0:a:0",
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
                "-af",
                audio_filter,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
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
                "ffmpeg",
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
