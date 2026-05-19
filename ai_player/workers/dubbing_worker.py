from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from faster_whisper import WhisperModel
from PySide6.QtCore import QThread, Signal

from ai_player.core.config import PROJECT_ROOT, AppConfig
from ai_player.core.gpu import ctranslate2_cuda_available, cuda_runtime_files_available
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.services.audio_matcher import (
    audio_duration_seconds,
    extract_audio_range,
    match_tts_to_reference,
    profile_reference_audio,
)
from ai_player.services.capture_sources import (
    capture_microphone_audio,
    capture_system_audio,
    capture_system_microphone_audio,
)
from ai_player.services.ffmpeg import ProcessCancelled, run_ffmpeg_cancelable
from ai_player.services.subtitle_ocr import recognize_hard_subtitles
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation import VietnameseTranslator
from ai_player.services.tts import create_tts_provider, normalize_tts_provider, select_voice_for_gender

PendingAudio = tuple[float, float, Path, str, str]
PLAYBACK_AUDIO_LEAD_SECONDS = 0.25
PLAYBACK_SYNC_HOLD_TOLERANCE_SECONDS = 0.35
SUPPORTED_AUDIO_SOURCES = {
    "original",
    "system",
    "microphone",
    "system_microphone",
    "transcript",
    "subtitle",
    "document_editor",
}


@dataclass(frozen=True)
class TranscriptEntry:
    start: float
    end: float | None
    text: str


class DubbingWorker(QThread):
    status_changed = Signal(str)
    segment_ready = Signal(str, str)
    audio_started = Signal(float)
    playback_pause_requested = Signal(str)
    playback_resume_requested = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        video_path: str,
        get_time_ms: Callable[[], int],
        is_playing: Callable[[], bool],
        config: AppConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._get_time_ms = get_time_ms
        self._is_playing = is_playing
        self._config = config
        self._stop_requested = False
        self._translator = VietnameseTranslator(self._config)
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._tts_provider = create_tts_provider(self._config)
        self._model: WhisperModel | None = None
        self._whisper_device = _effective_whisper_device(config.whisper_device)
        self._whisper_compute_type = config.whisper_compute_type
        self._next_segment_start = 0.0
        self._covered_until = 0.0
        self._prepared_segments = 0
        self._buffering = True
        self._pause_requested_by_worker = False
        self._sync_hold_requested = False
        self._active_audio_processes: list[subprocess.Popen] = []
        self._temp_dir: Path | None = None
        self._pending_audio: list[PendingAudio] = []
        self._scheduled_audio_until = 0.0
        self._last_video_time: float | None = None
        self._last_wall_time: float | None = None
        self._scheduled_text_keys: list[tuple[str, float]] = []
        self._state_lock = threading.RLock()
        self._segment_executor: ThreadPoolExecutor | None = None
        self._segment_futures: dict[Future[None], float] = {}

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_active_audio()

    def run(self) -> None:
        offline_env: OfflineEnvironmentToken | None = None
        try:
            if self._config.audio_source not in SUPPORTED_AUDIO_SOURCES:
                raise RuntimeError(_unsupported_audio_source_message(self._config.audio_source))
            offline_env = self._configure_offline_environment()
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-"))
            if self._config.audio_source in {"transcript", "document_editor"}:
                self._run_transcript_source()
                return

            if self._config.audio_source != "subtitle":
                self.status_changed.emit("\u0110ang t\u1ea3i Whisper...")
                self._validate_whisper_model()
                self._model = self._load_whisper_model()
            current = self._get_time_ms() / 1000.0
            self._next_segment_start = max(
                0.0,
                current + self._config.dubbing_start_delay_seconds,
            )
            self._covered_until = self._next_segment_start
            self._scheduled_audio_until = self._next_segment_start
            if self._is_live_capture_source():
                self.status_changed.emit("\u0110ang capture ngu\u1ed3n live \u0111\u1ec3 l\u1ed3ng ti\u1ebfng...")
            else:
                self._request_pause("\u0110ang chu\u1ea9n b\u1ecb gi\u1ecdng Vi\u1ec7t...")
            self.status_changed.emit("\u0110ang t\u1ea1o b\u1ed9 \u0111\u1ec7m l\u1ed3ng ti\u1ebfng Vi\u1ec7t...")
            if self._can_process_segments_async():
                self._segment_executor = ThreadPoolExecutor(max_workers=1)

            while not self._stop_requested:
                current = self._get_time_ms() / 1000.0
                if self._playback_position_jumped(current):
                    self._reset_schedule(current + self._config.dubbing_start_delay_seconds)
                    time.sleep(0.1)
                    continue

                self._cleanup_finished_audio()
                self._collect_segment_futures(current)
                self._release_sync_hold_if_ready(current)

                if self._is_playing():
                    if self._sync_hold_needed(current):
                        self._sync_hold_requested = True
                        self._request_pause("Tạm dừng âm nguồn để âm đích bắt kịp...")
                        time.sleep(0.05)
                        continue
                    self._launch_due_audio(current)
                    ready_ahead = self._covered_until - current
                    if (
                        not self._is_live_capture_source()
                        and ready_ahead < self._config.dubbing_min_ready_ahead_seconds
                    ):
                        self._buffering = True
                        self._request_pause("\u0110ang \u0111\u1ee3i gi\u1ecdng Vi\u1ec7t b\u1eaft k\u1ecbp...")

                lookahead_seconds = max(
                    self._config.segment_seconds * self._config.dubbing_lookahead_segments,
                    self._config.dubbing_min_ready_ahead_seconds + self._config.segment_seconds,
                )
                if self._next_segment_start <= current + lookahead_seconds:
                    if self._segment_executor is None:
                        self._process_segment(self._next_segment_start)
                        self._next_segment_start += self._config.segment_seconds
                        self._covered_until = max(self._covered_until, self._next_segment_start)
                    else:
                        self._submit_segment_work(current + lookahead_seconds)
                    self._resume_if_buffer_ready(current)
                else:
                    self._resume_if_buffer_ready(current)
                    time.sleep(0.1)
        except Exception as exc:
            if not self._stop_requested:
                self.failed.emit(_clean_message(exc))
        finally:
            self._shutdown_segment_executor()
            self._cleanup_temp_dir()
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _is_live_capture_source(self) -> bool:
        return self._config.audio_source in {"system", "microphone", "system_microphone"}

    def _can_process_segments_async(self) -> bool:
        return self._config.audio_source in {"original", "subtitle"}

    def _run_transcript_source(self) -> None:
        entries = _load_transcript_entries(self._config.transcript_path, self._config.segment_seconds)
        if not entries:
            self._buffering = False
            self._request_resume("Transcript không có nội dung để đọc")
            while not self._stop_requested:
                time.sleep(0.2)
            return
        current = self._get_time_ms() / 1000.0
        self._next_segment_start = max(0.0, current + self._config.dubbing_start_delay_seconds)
        self._covered_until = self._next_segment_start
        self._scheduled_audio_until = self._next_segment_start
        self._request_pause("\u0110ang chu\u1ea9n b\u1ecb transcript...")
        self.status_changed.emit("\u0110ang t\u1ea1o gi\u1ecdng Vi\u1ec7t t\u1eeb transcript...")

        next_index = 0
        while next_index < len(entries):
            entry = entries[next_index]
            if entry.end is None or entry.end >= current:
                break
            next_index += 1

        next_index = self._prepare_next_transcript_entries(entries, next_index, force_one=True)

        while not self._stop_requested:
            current = self._get_time_ms() / 1000.0
            self._cleanup_finished_audio()
            if self._is_playing():
                self._launch_due_audio(current)
            if next_index < len(entries):
                ready_ahead = self._covered_until - current
                target_ahead = max(
                    float(self._config.segment_seconds),
                    float(self._config.dubbing_min_ready_ahead_seconds),
                )
                with self._state_lock:
                    pending_audio_count = len(self._pending_audio)
                if ready_ahead <= target_ahead or pending_audio_count <= 1:
                    next_index = self._prepare_next_transcript_entries(entries, next_index)
            time.sleep(0.1)

    def _prepare_next_transcript_entries(
        self,
        entries: list[TranscriptEntry],
        start_index: int,
        force_one: bool = False,
    ) -> int:
        index = start_index
        prepared = 0
        current = self._get_time_ms() / 1000.0
        while index < len(entries):
            if self._stop_requested:
                return index
            entry = entries[index]
            index += 1
            if entry.end is not None and entry.end < current:
                continue
            self._prepare_transcript_entry(entry, index - 1)
            self._covered_until = max(
                self._covered_until,
                entry.end if entry.end is not None else entry.start + self._config.segment_seconds,
            )
            self._prepared_segments += 1
            prepared += 1
            current = self._get_time_ms() / 1000.0
            self._resume_if_buffer_ready(current)
            if self._is_playing():
                self._launch_due_audio(current)
            if force_one or not self._buffering:
                break
        if self._buffering and prepared == 0:
            self._buffering = False
            self._request_resume("L\u1ed3ng ti\u1ebfng Vi\u1ec7t t\u1eeb transcript \u0111\u00e3 s\u1eb5n s\u00e0ng")
        return index

    def _prepare_transcript_entry(self, entry: TranscriptEntry, index: int) -> None:
        if self._temp_dir is None:
            return
        original = self._clean_transcript_text(entry.text.strip(), self._selected_whisper_language())
        if not original:
            return
        segment_ms = int(entry.start * 1000)
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        tts_path = self._temp_dir / f"vi-transcript-{segment_ms}-{index}.{tts_suffix}"

        self.status_changed.emit(f"\u0110ang d\u1ecbch transcript t\u1ea1i {_format_hhmmss(entry.start)}...")
        translated = self._translator.translate(original, self._selected_whisper_language())
        if _tts_disabled(self._config):
            self.segment_ready.emit(original, translated)
            with self._state_lock:
                self._scheduled_audio_until = max(
                    self._scheduled_audio_until,
                    entry.end if entry.end is not None else entry.start + self._config.segment_seconds,
                )
            return
        self.status_changed.emit(f"\u0110ang t\u1ea1o gi\u1ecdng Vi\u1ec7t t\u1ea1i {_format_hhmmss(entry.start)}...")
        self._tts_provider.synthesize(translated, tts_path, voice=self._config.tts_voice)
        final_path = self._trim_leading_silence(tts_path)
        final_duration = audio_duration_seconds(final_path)
        with self._state_lock:
            scheduled_start = max(entry.start, self._scheduled_audio_until)
            self._scheduled_audio_until = scheduled_start + max(0.05, final_duration)
            self._pending_audio.append((scheduled_start, entry.start, final_path, original, translated))
            self._pending_audio.sort(key=lambda item: item[0])

    def _reset_schedule(self, start_seconds: float) -> None:
        self._stop_active_audio()
        if self._segment_executor is not None:
            self._shutdown_segment_executor()
            if self._can_process_segments_async() and not self._stop_requested:
                self._segment_executor = ThreadPoolExecutor(max_workers=1)
        self._next_segment_start = max(0.0, start_seconds)
        self._covered_until = self._next_segment_start
        with self._state_lock:
            self._prepared_segments = 0
            self._pending_audio.clear()
            self._scheduled_text_keys.clear()
            self._scheduled_audio_until = self._next_segment_start
        self._last_video_time = self._next_segment_start
        self._last_wall_time = time.monotonic()
        self._buffering = True
        self._request_pause("\u0110ang \u0111\u1ed3ng b\u1ed9 l\u1ea1i gi\u1ecdng Vi\u1ec7t...")

    def _submit_segment_work(self, target_seconds: float) -> None:
        if self._segment_executor is None:
            return
        max_pending = max(1, int(self._config.dubbing_lookahead_segments))
        while (
            not self._stop_requested
            and len(self._segment_futures) < max_pending
            and self._next_segment_start <= target_seconds
        ):
            start_seconds = self._next_segment_start
            future = self._segment_executor.submit(self._process_segment, start_seconds)
            self._segment_futures[future] = start_seconds
            self._next_segment_start += self._config.segment_seconds

    def _collect_segment_futures(self, current_seconds: float) -> None:
        completed = [future for future in self._segment_futures if future.done()]
        for future in completed:
            start_seconds = self._segment_futures.pop(future)
            future.result()
            self._covered_until = max(self._covered_until, start_seconds + self._config.segment_seconds)
            self._resume_if_buffer_ready(current_seconds)

    def _cancel_segment_futures(self) -> None:
        for future in list(self._segment_futures):
            future.cancel()
        self._segment_futures.clear()

    def _shutdown_segment_executor(self) -> None:
        self._cancel_segment_futures()
        if self._segment_executor is None:
            return
        self._segment_executor.shutdown(wait=True, cancel_futures=True)
        self._segment_executor = None

    def _playback_position_jumped(self, current_seconds: float) -> bool:
        now = time.monotonic()
        if self._last_video_time is None:
            self._last_video_time = current_seconds
            self._last_wall_time = now
            return False

        previous = self._last_video_time
        previous_wall = self._last_wall_time or now
        self._last_video_time = current_seconds
        self._last_wall_time = now
        if not self._is_playing():
            return False

        delta = current_seconds - previous
        elapsed_wall = max(0.0, now - previous_wall)
        allowed_forward_jump = elapsed_wall + max(5.0, self._config.segment_seconds)
        if delta < -1.0:
            return True
        return delta > allowed_forward_jump

    def _configure_offline_environment(self) -> OfflineEnvironmentToken:
        return push_hf_offline_environment(
            self._config.whisper_offline or self._config.local_translation_offline or self._config.vieneu_tts_offline
        )

    def _selected_whisper_language(self) -> str | None:
        language = str(self._config.source_language or "auto").strip().lower()
        return None if language in {"", "auto"} else language

    def _validate_whisper_model(self) -> None:
        if not self._config.whisper_offline:
            return
        model_path = Path(self._config.whisper_model)
        if not model_path.exists():
            raise RuntimeError(
                "Thi\u1ebfu model Whisper offline. Ch\u1ea1y scripts\\download_offline_models.ps1 "
                "ho\u1eb7c scripts\\download_whisper_model.ps1 \u0111\u1ec3 t\u1ea3i models\\asr\\faster-whisper-base."
            )

    def _load_whisper_model(self) -> WhisperModel:
        try:
            return WhisperModel(
                self._config.whisper_model,
                device=self._whisper_device,
                compute_type=self._whisper_compute_type,
            )
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self.status_changed.emit("Whisper CPU không hỗ trợ float16, chuyển sang int8...")
                return self._switch_whisper_to_cpu(exc)
            if self._whisper_device == "cpu":
                raise
            self.status_changed.emit("Whisper không chạy được CUDA/Auto, chuyển sang CPU...")
            return self._switch_whisper_to_cpu(exc)

    def _switch_whisper_to_cpu(self, _cause: Exception | None = None) -> WhisperModel:
        self._whisper_device = "cpu"
        self._whisper_compute_type = "int8"
        self._model = WhisperModel(
            self._config.whisper_model,
            device=self._whisper_device,
            compute_type=self._whisper_compute_type,
        )
        return self._model

    def _transcribe_with_fallback(self, wav_path: Path):
        if self._model is None:
            self._model = self._load_whisper_model()
        try:
            return self._model.transcribe(
                str(wav_path),
                beam_size=1,
                vad_filter=True,
                language=self._selected_whisper_language(),
            )
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self.status_changed.emit("Whisper CPU không hỗ trợ compute hiện tại, chuyển sang int8...")
                self._switch_whisper_to_cpu(exc)
                return self._model.transcribe(
                    str(wav_path),
                    beam_size=1,
                    vad_filter=True,
                    language=self._selected_whisper_language(),
                )
            if self._whisper_device == "cpu":
                raise
            self.status_changed.emit("Whisper lỗi CUDA/CUBLAS, chuyển sang CPU...")
            self._switch_whisper_to_cpu(exc)
            return self._model.transcribe(
                str(wav_path),
                beam_size=1,
                vad_filter=True,
                language=self._selected_whisper_language(),
            )

    def _resume_if_buffer_ready(self, current_seconds: float) -> None:
        ready_ahead = self._covered_until - current_seconds
        required_segments = self._config.dubbing_prebuffer_segments
        required_ready_ahead = self._config.dubbing_min_ready_ahead_seconds
        if self._config.audio_source in {"transcript", "document_editor"}:
            required_segments = 1
            required_ready_ahead = 0.5
        with self._state_lock:
            prepared_segments = self._prepared_segments
        if self._buffering and prepared_segments >= required_segments and ready_ahead >= required_ready_ahead:
            self._buffering = False
            self._launch_due_audio(current_seconds)
            self._request_resume("L\u1ed3ng ti\u1ebfng Vi\u1ec7t \u0111\u00e3 s\u1eb5n s\u00e0ng")

    def _process_segment(self, start_seconds: float) -> None:
        if self._temp_dir is None:
            return
        if self._config.audio_source != "subtitle" and self._model is None:
            return

        safe_start = int(start_seconds * 1000)
        wav_path = self._temp_dir / f"source-{safe_start}.wav"
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"

        if self._config.audio_source == "subtitle":
            self._process_subtitle_segment(start_seconds, tts_suffix)
            return

        self.status_changed.emit(f"\u0110ang nghe \u0111o\u1ea1n {_format_hhmmss(start_seconds)}...")
        with measure_stage("dubbing", "extract", start=f"{start_seconds:.3f}", source=self._config.audio_source):
            self._extract_audio(start_seconds, wav_path)

        with measure_stage("dubbing", "asr", start=f"{start_seconds:.3f}"):
            segments, info = self._transcribe_with_fallback(wav_path)
            recognized_segments = [segment for segment in segments if segment.text and segment.text.strip()]
        if not recognized_segments:
            with self._state_lock:
                self._prepared_segments += 1
            return

        for index, speech_segment in enumerate(recognized_segments):
            if self._stop_requested:
                return

            original = self._clean_transcript_text(speech_segment.text.strip(), getattr(info, "language", None))
            absolute_start = start_seconds + max(0.0, float(speech_segment.start or 0.0))
            if self._is_duplicate_nearby_text(original, absolute_start):
                continue
            speech_start = max(0.0, float(speech_segment.start or 0.0))
            speech_end = max(speech_start + 0.25, float(speech_segment.end or speech_start + 0.25))
            speech_duration = max(0.25, speech_end - speech_start)
            segment_ms = int(absolute_start * 1000)
            tts_path = self._temp_dir / f"vi-{segment_ms}-{index}.{tts_suffix}"
            reference_path = self._temp_dir / f"ref-{segment_ms}-{index}.wav"
            matched_path = self._temp_dir / f"vi-{segment_ms}-{index}-matched.wav"

            self.status_changed.emit(f"\u0110ang d\u1ecbch c\u00e2u t\u1ea1i {_format_hhmmss(absolute_start)}...")
            with measure_stage("dubbing", "translate", start=f"{absolute_start:.3f}"):
                translated = self._translator.translate(original, info.language)
            if _tts_disabled(self._config):
                self.segment_ready.emit(original, translated)
                self._remember_scheduled_text(original, absolute_start)
                continue

            with measure_stage("dubbing", "reference", start=f"{absolute_start:.3f}"):
                extract_audio_range(
                    wav_path,
                    speech_start,
                    speech_duration,
                    reference_path,
                    cancel_callback=self._is_stop_requested,
                )
                if self._config.dubbing_auto_voice_gender:
                    audio_profile = profile_reference_audio(reference_path)
                else:
                    audio_profile = None
            voice = self._config.tts_voice
            if audio_profile is not None:
                voice = select_voice_for_gender(
                    self._config.tts_provider,
                    self._config,
                    audio_profile.gender,
                )

            self.status_changed.emit(
                f"\u0110ang t\u1ea1o gi\u1ecdng Vi\u1ec7t t\u1ea1i {_format_hhmmss(absolute_start)}..."
            )
            with measure_stage("dubbing", "tts", start=f"{absolute_start:.3f}"):
                self._tts_provider.synthesize(translated, tts_path, voice=voice)
            if self._stop_requested:
                return
            with measure_stage("dubbing", "postprocess", start=f"{absolute_start:.3f}"):
                trimmed_path = self._trim_leading_silence(tts_path)
                if self._stop_requested:
                    return
                final_path = match_tts_to_reference(
                    reference_path=reference_path,
                    tts_path=trimmed_path,
                    output_path=matched_path,
                    target_duration_seconds=speech_duration,
                    config=self._config,
                    cancel_callback=self._is_stop_requested,
                )
            final_duration = audio_duration_seconds(final_path)
            with self._state_lock:
                scheduled_start = max(absolute_start, self._scheduled_audio_until)
                self._scheduled_audio_until = scheduled_start + max(0.05, final_duration)
                self._pending_audio.append((scheduled_start, absolute_start, final_path, original, translated))
            self._remember_scheduled_text(original, absolute_start)

        with self._state_lock:
            self._pending_audio.sort(key=lambda item: item[0])
            self._prepared_segments += 1

    def _process_subtitle_segment(self, start_seconds: float, tts_suffix: str) -> None:
        if self._temp_dir is None:
            return
        self.status_changed.emit(
            f"\u0110ang OCR ph\u1ee5 \u0111\u1ec1 c\u1ee9ng t\u1ea1i {_format_hhmmss(start_seconds)}..."
        )
        subtitle_segments = recognize_hard_subtitles(
            self._video_path,
            start_seconds,
            self._config.segment_seconds,
            self._temp_dir,
            self._config.source_language,
        )
        if not subtitle_segments:
            with self._state_lock:
                self._prepared_segments += 1
            return

        for index, subtitle_segment in enumerate(subtitle_segments):
            if self._stop_requested:
                return
            original = self._clean_transcript_text(subtitle_segment.text.strip(), self._selected_whisper_language())
            absolute_start = subtitle_segment.start
            if self._is_duplicate_nearby_text(original, absolute_start):
                continue
            duration = max(0.5, subtitle_segment.end - subtitle_segment.start)
            segment_ms = int(absolute_start * 1000)
            tts_path = self._temp_dir / f"vi-subtitle-{segment_ms}-{index}.{tts_suffix}"

            self.status_changed.emit(
                f"\u0110ang d\u1ecbch ph\u1ee5 \u0111\u1ec1 t\u1ea1i {_format_hhmmss(absolute_start)}..."
            )
            translated = self._translator.translate(original, self._selected_whisper_language())
            if _tts_disabled(self._config):
                self.segment_ready.emit(original, translated)
                self._remember_scheduled_text(original, absolute_start)
                continue
            self.status_changed.emit(
                f"\u0110ang t\u1ea1o gi\u1ecdng Vi\u1ec7t t\u1ea1i {_format_hhmmss(absolute_start)}..."
            )
            self._tts_provider.synthesize(translated, tts_path, voice=self._config.tts_voice)
            final_path = self._trim_leading_silence(tts_path)
            final_duration = audio_duration_seconds(final_path)
            with self._state_lock:
                scheduled_start = max(absolute_start, self._scheduled_audio_until)
                self._scheduled_audio_until = scheduled_start + max(0.05, final_duration, duration * 0.25)
                self._pending_audio.append((scheduled_start, absolute_start, final_path, original, translated))
            self._remember_scheduled_text(original, absolute_start)

        with self._state_lock:
            self._pending_audio.sort(key=lambda item: item[0])
            self._prepared_segments += 1

    def _is_duplicate_nearby_text(self, text: str, start_seconds: float) -> bool:
        key = _text_key(text)
        if not key:
            return False
        window_seconds = max(30.0, self._config.segment_seconds * 3.0)
        with self._state_lock:
            self._scheduled_text_keys = [
                (known_key, known_start)
                for known_key, known_start in self._scheduled_text_keys
                if start_seconds - known_start <= window_seconds
            ]
            return any(
                abs(start_seconds - known_start) <= window_seconds and _text_keys_similar(known_key, key)
                for known_key, known_start in self._scheduled_text_keys
            )

    def _remember_scheduled_text(self, text: str, start_seconds: float) -> None:
        key = _text_key(text)
        if key:
            with self._state_lock:
                self._scheduled_text_keys.append((key, start_seconds))

    def _extract_audio(self, start_seconds: float, wav_path: Path) -> None:
        if self._config.audio_source == "system":
            capture_system_audio(
                wav_path,
                self._config.segment_seconds,
                device_name=self._config.capture_system_device,
                backend=self._config.capture_backend,
            )
            return
        if self._config.audio_source == "microphone":
            capture_microphone_audio(
                wav_path,
                self._config.segment_seconds,
                device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
            )
            return
        if self._config.audio_source == "system_microphone":
            capture_system_microphone_audio(
                wav_path,
                self._config.segment_seconds,
                system_device_name=self._config.capture_system_device,
                microphone_device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
            )
            return

        args: list[object] = []
        if self._is_http_source(self._video_path):
            args.extend(
                [
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                ]
            )
        args.extend(
            [
                "-ss",
                f"{start_seconds:.3f}",
                "-t",
                str(self._config.segment_seconds),
                "-i",
                self._video_path,
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-y",
                str(wav_path),
            ]
        )
        run_ffmpeg_cancelable(args, cancel_callback=self._is_stop_requested, loglevel="fatal")

    def _clean_transcript_text(self, text: str, source_language: str | None = None) -> str:
        return self._transcript_cleaner.clean(text, source_language)

    def _trim_leading_silence(self, audio_path: Path) -> Path:
        trimmed_path = audio_path.with_name(f"{audio_path.stem}-trimmed{audio_path.suffix}")
        command = [
            "-i",
            str(audio_path),
            "-af",
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB",
            "-y",
            str(trimmed_path),
        ]
        try:
            run_ffmpeg_cancelable(command, cancel_callback=self._is_stop_requested)
        except ProcessCancelled:
            raise
        except Exception:
            return audio_path
        if trimmed_path.exists() and trimmed_path.stat().st_size > 0:
            return trimmed_path
        return audio_path

    def _is_stop_requested(self) -> bool:
        return self._stop_requested

    @staticmethod
    def _is_http_source(value: str) -> bool:
        return value.lower().startswith(("http://", "https://"))

    def _sync_hold_supported(self) -> bool:
        return self._config.audio_source not in {
            "system",
            "microphone",
            "system_microphone",
            "transcript",
            "document_editor",
        }

    def _has_active_audio(self) -> bool:
        return any(process.poll() is None for process in self._active_audio_processes)

    def _has_due_pending_audio(self, current_seconds: float, tolerance_seconds: float = 0.0) -> bool:
        if self._config.audio_source in {"transcript", "document_editor"}:
            with self._state_lock:
                return bool(self._pending_audio)
        threshold = current_seconds + PLAYBACK_AUDIO_LEAD_SECONDS - tolerance_seconds
        with self._state_lock:
            return any(item[0] <= threshold for item in self._pending_audio)

    def _sync_hold_needed(self, current_seconds: float) -> bool:
        return (
            self._sync_hold_supported()
            and self._has_active_audio()
            and self._has_due_pending_audio(current_seconds, PLAYBACK_SYNC_HOLD_TOLERANCE_SECONDS)
        )

    def _release_sync_hold_if_ready(self, current_seconds: float) -> None:
        if not self._sync_hold_requested:
            return
        if self._has_active_audio():
            return
        if self._has_due_pending_audio(current_seconds):
            self._launch_due_audio(current_seconds)
            return
        self._sync_hold_requested = False
        if not self._buffering:
            self._request_resume("Âm đích đã bắt kịp âm nguồn")

    def _launch_due_audio(self, current_seconds: float) -> bool:
        if any(process.poll() is None for process in self._active_audio_processes):
            return False

        if self._config.audio_source in {"transcript", "document_editor"}:
            with self._state_lock:
                ready = sorted(self._pending_audio, key=lambda item: item[0])
        else:
            with self._state_lock:
                ready = sorted(
                    [item for item in self._pending_audio if current_seconds >= item[0] - PLAYBACK_AUDIO_LEAD_SECONDS],
                    key=lambda item: item[0],
                )
        if not ready:
            return False

        selected = ready[0]
        with self._state_lock:
            if selected not in self._pending_audio:
                return False
            self._pending_audio.remove(selected)
        _, display_start, audio_path, original, translated = selected
        self.status_changed.emit("\u0110ang ph\u00e1t gi\u1ecdng ti\u1ebfng Vi\u1ec7t")
        self.audio_started.emit(display_start)
        self.segment_ready.emit(original, translated)
        command = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-volume",
            str(max(0, min(100, int(self._config.dubbing_voice_volume)))),
            str(audio_path),
        ]
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self._active_audio_processes.append(subprocess.Popen(command, startupinfo=startupinfo))
        return True

    def _request_pause(self, message: str) -> None:
        if self._pause_requested_by_worker:
            self.status_changed.emit(message)
            return
        self._pause_requested_by_worker = True
        self.playback_pause_requested.emit(message)

    def _request_resume(self, message: str) -> None:
        if not self._pause_requested_by_worker:
            self.status_changed.emit(message)
            return
        self._pause_requested_by_worker = False
        self.playback_resume_requested.emit(message)

    def _cleanup_finished_audio(self) -> None:
        self._active_audio_processes = [process for process in self._active_audio_processes if process.poll() is None]

    def _stop_active_audio(self) -> None:
        for process in self._active_audio_processes:
            _terminate_process(process)
        self._active_audio_processes.clear()

    def _cleanup_temp_dir(self) -> None:
        self._tts_provider.close()
        self._stop_active_audio()
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = None
        with self._state_lock:
            self._pending_audio.clear()
            self._scheduled_audio_until = 0.0
            self._scheduled_text_keys.clear()
        self._last_video_time = None
        self._last_wall_time = None
        self._sync_hold_requested = False


def _clean_message(value: object) -> str:
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")


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


def _unsupported_audio_source_message(value: str) -> str:
    label = str(value or "ngu\u1ed3n n\u00e0y")
    supported = ", ".join(sorted(SUPPORTED_AUDIO_SOURCES))
    return f"Khong ho tro nguon '{label}'. Cac nguon hop le: {supported}."


def _tts_disabled(config: AppConfig) -> bool:
    return normalize_tts_provider(config.tts_provider) == "none"


def _load_transcript_entries(path_value: str, segment_seconds: int) -> list[TranscriptEntry]:
    path = Path(str(path_value or "").strip())
    if not path.exists() or not path.is_file():
        raise RuntimeError("H\u00e3y ch\u1ecdn t\u1ec7p transcript tr\u01b0\u1edbc khi b\u1eadt l\u1ed3ng ti\u1ebfng.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".srt", ".vtt"} or "-->" in text:
        return _parse_timed_transcript(text)
    entries = _parse_bracket_timed_transcript(text)
    if entries:
        return entries
    return _parse_plain_transcript(text, segment_seconds)


def _parse_timed_transcript(text: str) -> list[TranscriptEntry]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized)
    entries: list[TranscriptEntry] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue
        start_text, end_text = [part.strip() for part in lines[time_index].split("-->", 1)]
        start = _parse_timestamp(start_text)
        end = _parse_timestamp(end_text)
        body = " ".join(lines[time_index + 1 :]).strip()
        body = re.sub(r"<[^>]+>", "", body).strip()
        if start is not None and body:
            entries.append(TranscriptEntry(start=start, end=end, text=body))
    return entries


def _parse_bracket_timed_transcript(text: str) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []
    for line in text.splitlines():
        match = re.match(r"\s*\[?(\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{1,3})?)\]?\s+(.+?)\s*$", line)
        if not match:
            continue
        start = _parse_timestamp(match.group(1))
        body = match.group(2).strip()
        if start is not None and body:
            entries.append(TranscriptEntry(start=start, end=None, text=body))
    return _fill_missing_transcript_ends(entries)


def _parse_plain_transcript(text: str, segment_seconds: int) -> list[TranscriptEntry]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    step = max(1.0, float(segment_seconds))
    return [TranscriptEntry(start=index * step, end=(index + 1) * step, text=line) for index, line in enumerate(lines)]


def _fill_missing_transcript_ends(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    filled: list[TranscriptEntry] = []
    for index, entry in enumerate(entries):
        next_start = entries[index + 1].start if index + 1 < len(entries) else entry.start + 5.0
        filled.append(TranscriptEntry(start=entry.start, end=max(entry.start + 0.25, next_start), text=entry.text))
    return filled


def _parse_timestamp(value: str) -> float | None:
    head = str(value or "").strip().split()[0].replace(",", ".")
    parts = head.split(":")
    try:
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return None
    return None


def _format_hhmmss(value: object) -> str:
    try:
        seconds_value = float(value or 0)
    except Exception:
        seconds_value = 0.0
    total_seconds = max(0, int(seconds_value))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _text_key(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _text_keys_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def _effective_whisper_device(value: str) -> str:
    device = str(value or "auto").strip().lower()
    if device == "cpu":
        return "cpu"
    if device == "cuda":
        return "cuda" if _cuda_runtime_available() else "cpu"
    if device == "auto":
        return "cuda" if _cuda_runtime_available() else "cpu"
    return device


def _cuda_runtime_available() -> bool:
    search_roots = [Path(value) for value in (os.environ.get("CUDA_PATH"),) if value]
    search_roots.append(PROJECT_ROOT / ".venv")
    return ctranslate2_cuda_available() or cuda_runtime_files_available(*search_roots)
