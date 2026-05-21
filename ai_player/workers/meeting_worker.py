from __future__ import annotations

import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.config import AppConfig
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.services.capture_sources import capture_system_microphone_audio
from ai_player.services.ffmpeg import ffmpeg_executable, ffplay_executable
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider, normalize_tts_provider
from ai_player.services.whisper_runtime import (
    SharedWhisperModel,
    get_shared_whisper_model,
    whisper_transcribe_kwargs,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type as shared_whisper_compute_type,
)
from ai_player.workers.dubbing_worker import _effective_whisper_device


@dataclass(frozen=True)
class MeetingResult:
    started_at: datetime
    audio_path: Path
    transcript_path: Path
    transcript_text: str


class MeetingWorker(QThread):
    status_changed = Signal(str)
    elapsed_changed = Signal(str)
    segment_ready = Signal(str, str)
    finished_successfully = Signal(object)
    failed = Signal(str)

    def __init__(self, output_dir: Path, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._output_dir = output_dir
        self._config = config
        self._stop_requested = False
        self._started_at = datetime.now()
        self._started_monotonic = time.monotonic()
        self._whisper_device = _effective_whisper_device(config.whisper_device)
        self._whisper_compute_type = shared_whisper_compute_type(config.whisper_compute_type, self._whisper_device)
        self._model: SharedWhisperModel | None = None
        self._translator = None
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._tts_provider = None
        self._playback_queue: queue.Queue[Path | None] | None = None
        self._playback_thread: threading.Thread | None = None
        self._active_playback_process: subprocess.Popen | None = None
        self._playback_lock = threading.Lock()

    @property
    def started_at(self) -> datetime:
        return self._started_at

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        temp_dir: Path | None = None
        offline_env: OfflineEnvironmentToken | None = None
        try:
            offline_env = self._configure_offline_environment()
            self._validate_whisper_model()
            self._output_dir.mkdir(parents=True, exist_ok=True)
            stem = self._started_at.strftime("%Y%m%d-%H%M%S")
            audio_path = self._output_dir / f"{stem}.wav"
            transcript_path = self._output_dir / f"{stem}.txt"

            temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-meeting-live-"))
            self._model = self._load_model()
            self._translator = get_shared_vietnamese_translator(self._config)
            self._tts_provider = None if _tts_disabled(self._config) else create_tts_provider(self._config)
            self._start_playback_worker()
            chunk_paths: list[Path] = []
            transcript_lines: list[str] = []
            transcript_lock = threading.Lock()
            processor_errors: list[Exception] = []
            work_queue: queue.Queue[tuple[Path, float, int] | None] = queue.Queue()
            chunk_seconds = max(3, min(10, int(self._config.segment_seconds or 6)))
            offset_seconds = 0.0

            def process_chunks() -> None:
                while True:
                    item = work_queue.get()
                    try:
                        if item is None:
                            return
                        chunk_path, chunk_offset, chunk_index = item
                        lines = self._process_chunk(chunk_path, chunk_offset, temp_dir, chunk_index)
                        if lines:
                            with transcript_lock:
                                transcript_lines.extend(lines)
                    except Exception as exc:
                        processor_errors.append(exc)
                        self._stop_requested = True
                    finally:
                        work_queue.task_done()

            processor = threading.Thread(target=process_chunks, daemon=True)
            processor.start()

            self.status_changed.emit("Đang ghi, nhận diện và lồng tiếng meeting...")
            while not self._stop_requested:
                self.elapsed_changed.emit(_format_elapsed(time.monotonic() - self._started_monotonic))
                chunk_path = temp_dir / f"meeting-chunk-{len(chunk_paths):05d}.wav"
                with measure_stage("meeting", "capture", chunk=len(chunk_paths), seconds=chunk_seconds):
                    capture_system_microphone_audio(
                        chunk_path,
                        chunk_seconds,
                        system_device_name=self._config.capture_system_device,
                        microphone_device_name=self._config.capture_microphone_device,
                        backend=self._config.capture_backend,
                    )
                if chunk_path.exists() and chunk_path.stat().st_size > 0:
                    chunk_index = len(chunk_paths)
                    chunk_paths.append(chunk_path)
                    work_queue.put((chunk_path, offset_seconds, chunk_index))
                offset_seconds += chunk_seconds

            if not chunk_paths:
                raise RuntimeError("Meeting không tạo được file âm thanh.")

            self.status_changed.emit("Đã dừng ghi. Đang chờ lồng tiếng hoàn tất trước khi xuất file...")
            work_queue.put(None)
            work_queue.join()
            processor.join(timeout=2.0)
            if processor_errors:
                raise processor_errors[0]
            self._finish_playback_worker(wait=True)
            self._export_audio(chunk_paths, audio_path, temp_dir)
            with transcript_lock:
                transcript_text = "\n".join(transcript_lines)
            if not transcript_text.strip():
                transcript_text = "(Không nhận diện được lời thoại.)"
            transcript_path.write_text(transcript_text.rstrip() + "\n", encoding="utf-8")
            self.finished_successfully.emit(
                MeetingResult(
                    started_at=self._started_at,
                    audio_path=audio_path,
                    transcript_path=transcript_path,
                    transcript_text=transcript_text,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._finish_playback_worker(wait=False)
            if self._tts_provider is not None:
                self._tts_provider.close()
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _configure_offline_environment(self) -> OfflineEnvironmentToken:
        return push_hf_offline_environment(self._config.whisper_offline)

    def _validate_whisper_model(self) -> None:
        if self._config.whisper_offline and not Path(self._config.whisper_model).exists():
            raise RuntimeError(
                "Thiếu model Whisper offline. Chạy scripts\\download_whisper_model.ps1 trước khi ghi meeting."
            )

    def _selected_whisper_language(self) -> str | None:
        language = str(self._config.source_language or "auto").strip().lower()
        return None if language in {"", "auto"} else language

    def _load_model(self) -> SharedWhisperModel:
        try:
            return get_shared_whisper_model(
                self._config.whisper_model,
                device=self._whisper_device,
                compute_type=self._whisper_compute_type,
                local_files_only=self._config.whisper_offline,
            )
        except Exception:
            self._whisper_device = "cpu"
            self._whisper_compute_type = "int8"
            return get_shared_whisper_model(
                self._config.whisper_model,
                device=self._whisper_device,
                compute_type=self._whisper_compute_type,
                local_files_only=self._config.whisper_offline,
            )

    def _transcribe_segments(self, audio_path: Path):
        if self._model is None:
            self._model = self._load_model()
        kwargs = whisper_transcribe_kwargs(self._config, self._selected_whisper_language())
        try:
            return self._model.transcribe(str(audio_path), **kwargs)
        except Exception:
            if self._whisper_device == "cpu":
                raise
            self._whisper_device = "cpu"
            self._whisper_compute_type = "int8"
            self._model = self._load_model()
            return self._model.transcribe(str(audio_path), **kwargs)

    def _process_chunk(
        self,
        audio_path: Path,
        offset_seconds: float,
        temp_dir: Path,
        chunk_index: int,
    ) -> list[str]:
        with measure_stage("meeting", "asr", chunk=chunk_index):
            segments, info = self._transcribe_segments(audio_path)
        lines = []
        for segment_index, segment in enumerate(segments):
            text = self._transcript_cleaner.clean((segment.text or "").strip(), getattr(info, "language", None))
            if not text:
                continue
            start = offset_seconds + float(segment.start or 0.0)
            end = offset_seconds + float(segment.end or segment.start or 0.0)
            with measure_stage("meeting", "translate", chunk=chunk_index, segment=segment_index):
                translated = self._translate(text, getattr(info, "language", None))
            self.segment_ready.emit(text, translated)
            if _tts_disabled(self._config):
                lines.append(f"[{_format_timestamp(start)} - {_format_timestamp(end)}]\nGốc: {text}\nVI: {translated}")
                continue
            tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
            self._dub_segment(
                translated,
                temp_dir / f"meeting-tts-{chunk_index:05d}-{segment_index:03d}.{tts_suffix}",
            )
            lines.append(f"[{_format_timestamp(start)} - {_format_timestamp(end)}]\nGốc: {text}\nVI: {translated}")
        return lines

    def _translate(self, text: str, detected_language: str | None) -> str:
        if self._translator is None:
            self._translator = get_shared_vietnamese_translator(self._config)
        return self._translator.translate(text, detected_language or self._selected_whisper_language())

    def _dub_segment(self, text: str, output_path: Path) -> None:
        if _tts_disabled(self._config):
            return
        if self._tts_provider is None:
            self._tts_provider = create_tts_provider(self._config)
        self.status_changed.emit("Đang lồng tiếng đoạn meeting...")
        with measure_stage("meeting", "tts"):
            self._tts_provider.synthesize(text, output_path, voice=self._config.tts_voice)
        if not output_path.exists() or output_path.stat().st_size == 0:
            return
        if self._playback_queue is not None:
            self._playback_queue.put(output_path)

    def _start_playback_worker(self) -> None:
        if _tts_disabled(self._config) or self._playback_thread is not None:
            return
        self._playback_queue = queue.Queue(maxsize=8)
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()

    def _finish_playback_worker(self, *, wait: bool) -> None:
        queue_ref = self._playback_queue
        thread_ref = self._playback_thread
        if queue_ref is not None:
            if wait:
                queue_ref.put(None)
                queue_ref.join()
            else:
                try:
                    queue_ref.put(None, timeout=0.5)
                except queue.Full:
                    pass
        if thread_ref is not None:
            thread_ref.join(timeout=10.0 if wait else 1.0)
        if not wait:
            self._terminate_active_playback()
        self._playback_queue = None
        self._playback_thread = None

    def _playback_loop(self) -> None:
        queue_ref = self._playback_queue
        if queue_ref is None:
            return
        while True:
            audio_path = queue_ref.get()
            try:
                if audio_path is None:
                    return
                self._play_audio(audio_path)
            finally:
                queue_ref.task_done()

    def _play_audio(self, output_path: Path) -> None:
        command = [
            ffplay_executable(),
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-volume",
            str(max(0, min(100, int(self._config.dubbing_voice_volume)))),
            str(output_path),
        ]
        try:
            with measure_stage("meeting", "playback"):
                process = subprocess.Popen(command)
                with self._playback_lock:
                    self._active_playback_process = process
                process.wait()
        except Exception:
            pass
        finally:
            with self._playback_lock:
                self._active_playback_process = None

    def _terminate_active_playback(self) -> None:
        with self._playback_lock:
            process = self._active_playback_process
            self._active_playback_process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _export_audio(self, chunk_paths: list[Path], output_path: Path, temp_dir: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        list_path = temp_dir / "meeting-audio-list.txt"
        concat_lines = []
        for path in chunk_paths:
            concat_lines.append(f"file '{_ffmpeg_escape(path)}'")
        list_path.write_text(
            "\n".join(concat_lines) + "\n",
            encoding="utf-8",
        )
        command = [
            ffmpeg_executable(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            str(output_path),
        ]
        subprocess.run(command, check=True)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Meeting không tạo được file âm thanh.")


def _tts_disabled(config: AppConfig) -> bool:
    return normalize_tts_provider(config.tts_provider) == "none"


def _ffmpeg_escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "'\\''")


def _format_elapsed(elapsed_seconds: float) -> str:
    elapsed = max(0, int(elapsed_seconds))
    minutes, seconds = divmod(elapsed, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_timestamp(value: object) -> str:
    seconds_total = max(0, int(round(float(value or 0.0))))
    hours, remainder = divmod(seconds_total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
