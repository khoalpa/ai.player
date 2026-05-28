from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

from ai_player.core.app_logging import get_logger
from ai_player.core.config import AppConfig
from ai_player.core.i18n import ui_text
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.pipeline.transcript_source import (
    TranscriptEntry,
)
from ai_player.pipeline.transcript_source import (
    format_hhmmss as _format_hhmmss,
)
from ai_player.pipeline.transcript_source import (
    load_transcript_entries as _load_transcript_entries,
)
from ai_player.services.audio_matcher import (
    audio_duration_seconds,
    extract_audio_range,
    match_tts_to_reference,
)
from ai_player.services.audio_timeline import (
    OVERLAP_POLICY_AVOID_OVERLAP,
    normalize_overlap_policy,
)
from ai_player.services.capture_sources import (
    capture_microphone_audio,
    capture_system_audio,
    capture_system_microphone_audio,
)
from ai_player.services.ffmpeg import (
    ProcessCancelled,
    ffplay_executable,
    run_ffmpeg_cancelable,
    terminate_process,
)
from ai_player.services.ffmpeg import (
    make_silence as ffmpeg_make_silence,
)
from ai_player.services.speaker_voice_selector import VoiceGenderSelector, select_voice_for_reference
from ai_player.services.subtitle_ocr import recognize_hard_subtitles
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import (
    create_tts_provider,
    is_pathological_tts_duration,
    prepare_tts_text,
)
from ai_player.services.video_source import is_telegram_web_progressive_url
from ai_player.services.whisper_runtime import (
    SharedWhisperModel,
    get_shared_whisper_model,
    whisper_transcribe_kwargs,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type as shared_whisper_compute_type,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_device as _effective_whisper_device,
)
from ai_player.workers.asr_fallback import transcribe_model_with_device_fallback
from ai_player.workers.dubbing_schedule import DubbingAudioSchedule, PendingAudio
from ai_player.workers.worker_values import clamped_int as _clamped_int
from ai_player.workers.worker_values import clean_language as _clean_language
from ai_player.workers.worker_values import clean_message as _clean_message
from ai_player.workers.worker_values import clean_worker_text as _clean_worker_text
from ai_player.workers.worker_values import finite_seconds as _finite_seconds
from ai_player.workers.worker_values import int_value as _int_value
from ai_player.workers.worker_values import positive_int as _positive_int
from ai_player.workers.worker_values import segment_start_key as _segment_start_key
from ai_player.workers.worker_values import selected_source_language, voice_tts_suffix
from ai_player.workers.worker_values import tts_disabled as _tts_disabled

LOGGER = get_logger(__name__)

PLAYBACK_AUDIO_LEAD_SECONDS = 0.25
PLAYBACK_SYNC_HOLD_TOLERANCE_SECONDS = 0.35
DIRECT_HTTP_SOURCE_CACHE_SUFFIXES = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}
SUPPORTED_AUDIO_SOURCES = {
    "original",
    "system",
    "microphone",
    "system_microphone",
    "transcript",
    "subtitle",
    "document_editor",
}


class DubbingWorker(QThread):
    status_changed = Signal(str)
    segment_ready = Signal(str, str)
    subtitle_ready = Signal(float, float, str, str)
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
        self._translator = get_shared_vietnamese_translator(self._config)
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._tts_provider = create_tts_provider(self._config)
        self._voice_selector = VoiceGenderSelector(self._config)
        self._model: SharedWhisperModel | None = None
        self._whisper_device = _effective_whisper_device(config.whisper_device)
        self._whisper_compute_type = shared_whisper_compute_type(config.whisper_compute_type, self._whisper_device)
        self._next_segment_start = 0.0
        self._covered_until = 0.0
        self._prepared_segments = 0
        self._buffering = True
        self._pause_requested_by_worker = False
        self._sync_hold_requested = False
        self._active_audio_processes: list[subprocess.Popen] = []
        self._temp_dir: Path | None = None
        self._audio_schedule = DubbingAudioSchedule()
        self._last_video_time: float | None = None
        self._last_wall_time: float | None = None
        self._state_lock = threading.RLock()
        self._segment_executor: ThreadPoolExecutor | None = None
        self._segment_futures: dict[Future[None], float] = {}
        self._completed_segment_starts: set[int] = set()
        self._source_audio_cache_path: Path | None = None
        self._source_audio_cache_ready = False
        self._source_audio_cache_cancel = False
        self._source_audio_cache_thread: threading.Thread | None = None
        self._resync_requested = False
        self._realtime_cleanup_skip_warned = False

    @property
    def _pending_audio(self) -> list[PendingAudio]:
        return self._audio_schedule.pending_audio

    @_pending_audio.setter
    def _pending_audio(self, value: list[PendingAudio]) -> None:
        self._audio_schedule.pending_audio = value

    @property
    def _scheduled_audio_until(self) -> float:
        return self._audio_schedule.scheduled_until

    @_scheduled_audio_until.setter
    def _scheduled_audio_until(self, value: float) -> None:
        self._audio_schedule.scheduled_until = max(0.0, _finite_seconds(value, 0.0))

    @property
    def _scheduled_subtitle_keys(self) -> set[tuple[int, str]]:
        return self._audio_schedule.subtitle_keys

    @_scheduled_subtitle_keys.setter
    def _scheduled_subtitle_keys(self, value: set[tuple[int, str]]) -> None:
        self._audio_schedule.subtitle_keys = value

    @property
    def _scheduled_text_keys(self) -> list[tuple[str, float]]:
        return self._audio_schedule.text_keys

    @_scheduled_text_keys.setter
    def _scheduled_text_keys(self, value: list[tuple[str, float]]) -> None:
        self._audio_schedule.text_keys = value

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_active_audio()

    def request_resync(self) -> None:
        with self._state_lock:
            self._resync_requested = True

    def _tr(self, key: str, **kwargs: object) -> str:
        return ui_text(key, self._config.gui_language, **kwargs)

    def _emit_status(self, key: str, **kwargs: object) -> None:
        self.status_changed.emit(self._tr(key, **kwargs))

    def run(self) -> None:
        offline_env: OfflineEnvironmentToken | None = None
        try:
            if self._config.audio_source not in SUPPORTED_AUDIO_SOURCES:
                raise RuntimeError(
                    _unsupported_audio_source_message(self._config.audio_source, self._config.gui_language)
                )
            offline_env = self._configure_offline_environment()
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-"))
            self._start_source_audio_cache()
            if self._config.audio_source in {"transcript", "document_editor"}:
                self._run_transcript_source()
                return

            if self._config.audio_source != "subtitle":
                self._emit_status("worker_loading_whisper")
                self._validate_whisper_model()
                self._model = self._load_whisper_model()
            current = self._get_time_ms() / 1000.0
            self._next_segment_start = max(
                0.0,
                current + self._start_delay_seconds(),
            )
            self._covered_until = self._next_segment_start
            self._scheduled_audio_until = self._next_segment_start
            if self._is_live_capture_source():
                self._emit_status("worker_live_capture_starting")
            else:
                self._request_pause(self._tr("worker_preparing_target_voice"))
            self._emit_status("worker_buffering_target_voice")
            if self._can_process_segments_async():
                self._segment_executor = ThreadPoolExecutor(max_workers=self._segment_worker_count())

            while not self._stop_requested:
                current = self._get_time_ms() / 1000.0
                if self._consume_resync_request():
                    self._reset_schedule(current + self._start_delay_seconds())
                    time.sleep(0.1)
                    continue
                if self._playback_position_jumped(current):
                    self._reset_schedule(current + self._start_delay_seconds())
                    time.sleep(0.1)
                    continue

                self._cleanup_finished_audio()
                self._collect_segment_futures(current)
                self._release_sync_hold_if_ready(current)

                if self._is_playing():
                    if self._sync_hold_needed(current):
                        self._sync_hold_requested = True
                        self._request_pause(self._tr("worker_pause_for_target_sync"))
                        time.sleep(0.05)
                        continue
                    self._launch_due_audio(current)
                    ready_ahead = self._covered_until - current
                    if not self._is_live_capture_source() and ready_ahead < self._required_ready_ahead_seconds():
                        self._buffering = True
                        self._request_pause(self._tr("worker_waiting_target_voice"))

                segment_seconds = self._segment_seconds()
                lookahead_seconds = max(
                    segment_seconds * _positive_int(self._config.dubbing_lookahead_segments, default=1),
                    self._min_ready_ahead_seconds() + segment_seconds,
                )
                if self._next_segment_start <= current + lookahead_seconds:
                    if self._segment_executor is None:
                        self._process_segment(self._next_segment_start)
                        self._next_segment_start += segment_seconds
                        self._covered_until = max(self._covered_until, self._next_segment_start)
                    else:
                        self._submit_segment_work(current + lookahead_seconds)
                    self._resume_if_buffer_ready(current)
                else:
                    self._resume_if_buffer_ready(current)
                    time.sleep(0.1)
        except Exception as exc:
            if not self._stop_requested:
                LOGGER.exception("Realtime dubbing worker failed.")
                self.failed.emit(_format_worker_exception(exc))
        finally:
            self._shutdown_segment_executor()
            self._stop_source_audio_cache()
            self._cleanup_temp_dir()
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _is_live_capture_source(self) -> bool:
        return self._config.audio_source in {"system", "microphone", "system_microphone"}

    def _segment_seconds(self) -> float:
        return max(0.25, _finite_seconds(self._config.segment_seconds, 5.0))

    def _min_ready_ahead_seconds(self) -> float:
        return max(0.0, _finite_seconds(self._config.dubbing_min_ready_ahead_seconds, 0.0))

    def _start_delay_seconds(self) -> float:
        return max(0.0, _finite_seconds(self._config.dubbing_start_delay_seconds, 0.0))

    def _can_process_segments_async(self) -> bool:
        return self._config.audio_source in {"original", "subtitle"}

    def _run_transcript_source(self) -> None:
        entries = _load_transcript_entries(
            self._config.transcript_path,
            self._segment_seconds(),
            self._config.gui_language,
        )
        if not entries:
            self._buffering = False
            self._request_resume(self._tr("worker_transcript_empty"))
            while not self._stop_requested:
                time.sleep(0.2)
            return
        current = self._get_time_ms() / 1000.0
        self._next_segment_start = max(0.0, current + self._start_delay_seconds())
        self._covered_until = self._next_segment_start
        self._scheduled_audio_until = self._next_segment_start
        self._request_pause(self._tr("worker_preparing_transcript"))
        self._emit_status("worker_creating_voice_from_transcript")

        next_index = 0
        while next_index < len(entries):
            entry = entries[next_index]
            if entry.end is None or entry.end >= current:
                break
            next_index += 1

        next_index = self._prepare_next_transcript_entries(entries, next_index, force_one=True)

        while not self._stop_requested:
            current = self._get_time_ms() / 1000.0
            if self._consume_resync_request():
                self._reset_schedule(current + self._start_delay_seconds())
                next_index = 0
                while next_index < len(entries):
                    entry = entries[next_index]
                    if entry.end is None or entry.end >= current:
                        break
                    next_index += 1
                next_index = self._prepare_next_transcript_entries(entries, next_index, force_one=True)
                continue
            self._cleanup_finished_audio()
            if self._is_playing():
                self._launch_due_audio(current)
            if next_index < len(entries):
                ready_ahead = self._covered_until - current
                target_ahead = max(self._segment_seconds(), self._min_ready_ahead_seconds())
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
            entry_start = max(0.0, _finite_seconds(entry.start, 0.0))
            entry_end = self._transcript_entry_end(entry, entry_start)
            if entry.end is not None and entry_end < current:
                continue
            self._prepare_transcript_entry(entry, index - 1)
            self._covered_until = max(self._covered_until, entry_end)
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
            self._request_resume(self._tr("worker_transcript_dubbing_ready"))
        return index

    def _prepare_transcript_entry(self, entry: TranscriptEntry, index: int) -> None:
        if self._temp_dir is None:
            return
        entry_start = max(0.0, _finite_seconds(entry.start, 0.0))
        entry_end = self._transcript_entry_end(entry, entry_start)
        original = self._clean_transcript_text(_clean_worker_text(entry.text), self._selected_whisper_language())
        if not original:
            return
        segment_ms = int(entry_start * 1000)
        tts_suffix = voice_tts_suffix(self._config)
        tts_path = self._temp_dir / f"vi-transcript-{segment_ms}-{index}.{tts_suffix}"

        self._emit_status("worker_translating_transcript_at", time=_format_hhmmss(entry_start))
        translated = self._translator.translate(original, self._selected_whisper_language())
        if _tts_disabled(self._config):
            self.segment_ready.emit(original, translated)
            self._emit_subtitle_ready(entry_start, entry_end - entry_start, original, translated)
            with self._state_lock:
                self._scheduled_audio_until = max(self._scheduled_audio_until, entry_end)
            return
        duration = max(0.25, entry_end - entry_start)
        tts_text = prepare_tts_text(translated, self._config.target_language)
        if not tts_text:
            self._queue_silent_audio(
                entry_start,
                duration,
                tts_path.with_name(f"{tts_path.stem}-silence.wav"),
                original,
                translated,
            )
            return
        self._emit_status("worker_creating_target_voice_at", time=_format_hhmmss(entry_start))
        self._tts_provider.synthesize(tts_text, tts_path, voice=self._config.tts_voice)
        if is_pathological_tts_duration(tts_text, audio_duration_seconds(tts_path), duration):
            self._queue_silent_audio(
                entry_start,
                duration,
                tts_path.with_name(f"{tts_path.stem}-guard-silence.wav"),
                original,
                translated,
            )
            return
        final_path = tts_path if self._skip_tts_postprocess() else self._trim_leading_silence(tts_path)
        final_duration = audio_duration_seconds(final_path)
        self._emit_subtitle_ready(entry_start, duration, original, translated)
        self._queue_pending_audio(entry_start, final_duration, final_path, original, translated)

    def _transcript_entry_end(self, entry: TranscriptEntry, entry_start: float) -> float:
        if entry.end is None:
            return entry_start + self._segment_seconds()
        return max(entry_start + 0.25, _finite_seconds(entry.end, entry_start + self._segment_seconds()))

    def _reset_schedule(self, start_seconds: float) -> None:
        self._stop_active_audio()
        if self._segment_executor is not None:
            self._shutdown_segment_executor()
            if self._can_process_segments_async() and not self._stop_requested:
                self._segment_executor = ThreadPoolExecutor(max_workers=self._segment_worker_count())
        self._next_segment_start = max(0.0, start_seconds)
        self._covered_until = self._next_segment_start
        with self._state_lock:
            self._prepared_segments = 0
            self._audio_schedule.reset(self._next_segment_start)
            self._completed_segment_starts.clear()
        self._last_video_time = self._next_segment_start
        self._last_wall_time = time.monotonic()
        self._voice_selector.reset()
        self._buffering = True
        self._request_pause(self._tr("worker_resyncing_target_voice"))

    def _consume_resync_request(self) -> bool:
        with self._state_lock:
            if not self._resync_requested:
                return False
            self._resync_requested = False
            return True

    def _submit_segment_work(self, target_seconds: float) -> None:
        if self._segment_executor is None:
            return
        max_pending = _positive_int(self._config.dubbing_lookahead_segments, default=1)
        while (
            not self._stop_requested
            and len(self._segment_futures) < max_pending
            and self._next_segment_start <= target_seconds
        ):
            start_seconds = self._next_segment_start
            future = self._segment_executor.submit(self._process_segment, start_seconds)
            self._segment_futures[future] = start_seconds
            self._next_segment_start += self._segment_seconds()

    def _collect_segment_futures(self, current_seconds: float) -> None:
        completed = [future for future in self._segment_futures if future.done()]
        for future in completed:
            start_seconds = self._segment_futures.pop(future)
            future.result()
            self._completed_segment_starts.add(_segment_start_key(start_seconds))
            self._advance_covered_until()
            self._resume_if_buffer_ready(current_seconds)

    def _cancel_segment_futures(self) -> None:
        for future in list(self._segment_futures):
            future.cancel()
        self._segment_futures.clear()
        self._completed_segment_starts.clear()

    def _advance_covered_until(self) -> None:
        while _segment_start_key(self._covered_until) in self._completed_segment_starts:
            self._completed_segment_starts.remove(_segment_start_key(self._covered_until))
            self._covered_until += self._segment_seconds()

    def _segment_worker_count(self) -> int:
        configured = os.getenv("AI_PLAYER_DUBBING_SEGMENT_WORKERS", "").strip()
        if configured:
            try:
                return max(1, min(8, int(configured)))
            except (OverflowError, ValueError):
                pass
        if self._config.audio_source == "original":
            return 1
        cpu_count = os.cpu_count() or 2
        return max(1, min(4, cpu_count // 2, _positive_int(self._config.dubbing_lookahead_segments, default=1)))

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
        allowed_forward_jump = elapsed_wall + max(5.0, self._segment_seconds())
        if delta < -1.0:
            return True
        return delta > allowed_forward_jump

    def _configure_offline_environment(self) -> OfflineEnvironmentToken:
        return push_hf_offline_environment(
            self._config.whisper_offline or self._config.local_translation_offline or self._config.vieneu_tts_offline
        )

    def _selected_whisper_language(self) -> str | None:
        return selected_source_language(self._config)

    def _validate_whisper_model(self) -> None:
        if not self._config.whisper_offline:
            return
        model_path = Path(self._config.whisper_model)
        if not model_path.exists():
            raise RuntimeError(self._tr("worker_missing_whisper_offline"))

    def _load_whisper_model(self) -> SharedWhisperModel:
        try:
            return get_shared_whisper_model(
                self._config.whisper_model,
                device=self._whisper_device,
                compute_type=self._whisper_compute_type,
                local_files_only=self._config.whisper_offline,
            )
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self._emit_status("worker_whisper_cpu_float16_fallback")
                return self._switch_whisper_to_cpu(exc)
            if self._whisper_device == "cpu":
                raise
            self._emit_status("worker_whisper_cuda_fallback")
            return self._switch_whisper_to_cpu(exc)

    def _switch_whisper_to_cpu(self, _cause: Exception | None = None) -> SharedWhisperModel:
        self._whisper_device = "cpu"
        self._whisper_compute_type = "int8"
        self._model = get_shared_whisper_model(
            self._config.whisper_model,
            device=self._whisper_device,
            compute_type=self._whisper_compute_type,
            local_files_only=self._config.whisper_offline,
        )
        return self._model

    def _transcribe_with_fallback(self, wav_path: Path):
        if self._model is None:
            self._model = self._load_whisper_model()
        kwargs = whisper_transcribe_kwargs(self._config, self._selected_whisper_language())
        return transcribe_model_with_device_fallback(
            self._model,
            wav_path,
            kwargs,
            whisper_device=lambda: self._whisper_device,
            whisper_compute_type=lambda: self._whisper_compute_type,
            emit_status=lambda key: self._emit_status(key),
            switch_whisper_to_cpu=lambda exc: self._switch_whisper_to_cpu(exc),
        )

    def _resume_if_buffer_ready(self, current_seconds: float) -> None:
        ready_ahead = self._covered_until - current_seconds
        required_segments = _positive_int(self._config.dubbing_prebuffer_segments, default=1)
        required_ready_ahead = self._required_ready_ahead_seconds()
        if self._config.audio_source in {"transcript", "document_editor"}:
            required_segments = 1
        with self._state_lock:
            prepared_segments = self._prepared_segments
        if self._buffering and prepared_segments >= required_segments and ready_ahead >= required_ready_ahead:
            self._buffering = False
            self._launch_due_audio(current_seconds)
            self._request_resume(self._tr("worker_dubbing_ready"))

    def _required_ready_ahead_seconds(self) -> float:
        if self._config.audio_source in {"transcript", "document_editor"}:
            return 0.5
        configured_ready_ahead = self._min_ready_ahead_seconds()
        segment_ready_ahead = max(
            0.5,
            self._segment_seconds() * _positive_int(self._config.dubbing_prebuffer_segments, default=1),
        )
        return min(configured_ready_ahead, segment_ready_ahead)

    def _process_segment(self, start_seconds: float) -> None:
        if self._temp_dir is None:
            return
        if self._config.audio_source != "subtitle" and self._model is None:
            return

        start_seconds = max(0.0, _finite_seconds(start_seconds, 0.0))
        safe_start = int(start_seconds * 1000)
        wav_path = self._temp_dir / f"source-{safe_start}.wav"
        tts_suffix = voice_tts_suffix(self._config)

        if self._config.audio_source == "subtitle":
            self._process_subtitle_segment(start_seconds, tts_suffix)
            return

        self._emit_status("worker_listening_segment_at", time=_format_hhmmss(start_seconds))
        with measure_stage("dubbing", "extract", start=f"{start_seconds:.3f}", source=self._config.audio_source):
            self._extract_audio(start_seconds, wav_path)

        with measure_stage("dubbing", "asr", start=f"{start_seconds:.3f}"):
            segments, info = self._transcribe_with_fallback(wav_path)
            recognized_segments = [
                segment for segment in segments if _clean_worker_text(getattr(segment, "text", ""))
            ]
        if not recognized_segments:
            with self._state_lock:
                self._prepared_segments += 1
            return

        for index, speech_segment in enumerate(recognized_segments):
            if self._stop_requested:
                return

            source_language = _clean_language(getattr(info, "language", None))
            original = self._clean_transcript_text(
                _clean_worker_text(getattr(speech_segment, "text", "")),
                source_language,
            )
            speech_start = max(0.0, _finite_seconds(getattr(speech_segment, "start", 0.0), 0.0))
            absolute_start = start_seconds + speech_start
            if self._is_duplicate_nearby_text(original, absolute_start):
                continue
            speech_end = max(
                speech_start + 0.25,
                _finite_seconds(getattr(speech_segment, "end", None), speech_start + 0.25),
            )
            speech_duration = max(0.25, speech_end - speech_start)
            segment_ms = int(absolute_start * 1000)
            tts_path = self._temp_dir / f"vi-{segment_ms}-{index}.{tts_suffix}"
            reference_path = self._temp_dir / f"ref-{segment_ms}-{index}.wav"
            matched_path = self._temp_dir / f"vi-{segment_ms}-{index}-matched.wav"
            needs_reference_audio = self._needs_reference_audio()

            self._emit_status("worker_translating_sentence_at", time=_format_hhmmss(absolute_start))
            with measure_stage("dubbing", "translate", start=f"{absolute_start:.3f}"):
                translated = self._translator.translate(original, source_language)
            self._emit_subtitle_ready(absolute_start, speech_duration, original, translated)
            if _tts_disabled(self._config):
                self.segment_ready.emit(original, translated)
                self._remember_scheduled_text(original, absolute_start)
                continue
            tts_text = prepare_tts_text(translated, self._config.target_language)
            if not tts_text:
                self._queue_silent_audio(
                    absolute_start,
                    speech_duration,
                    self._temp_dir / f"vi-{segment_ms}-{index}-silence.wav",
                    original,
                    translated,
                )
                self._remember_scheduled_text(original, absolute_start)
                continue

            if needs_reference_audio:
                with measure_stage("dubbing", "reference", start=f"{absolute_start:.3f}"):
                    extract_audio_range(
                        wav_path,
                        speech_start,
                        speech_duration,
                        reference_path,
                        cancel_callback=self._is_stop_requested,
                    )
            else:
                reference_path = wav_path
            voice = self._config.tts_voice
            if self._config.dubbing_auto_voice_gender:
                voice = select_voice_for_reference(
                    reference_path,
                    provider=self._config.tts_provider,
                    config=self._config,
                    selector=self._voice_selector,
                ).voice

            self._emit_status("worker_creating_target_voice_at", time=_format_hhmmss(absolute_start))
            with measure_stage("dubbing", "tts", start=f"{absolute_start:.3f}"):
                self._tts_provider.synthesize(tts_text, tts_path, voice=voice)
            if self._stop_requested:
                return
            tts_duration = audio_duration_seconds(tts_path)
            if is_pathological_tts_duration(tts_text, tts_duration, speech_duration):
                self._queue_silent_audio(
                    absolute_start,
                    speech_duration,
                    self._temp_dir / f"vi-{segment_ms}-{index}-guard-silence.wav",
                    original,
                    translated,
                )
                self._remember_scheduled_text(original, absolute_start)
                continue
            with measure_stage("dubbing", "postprocess", start=f"{absolute_start:.3f}"):
                if self._skip_tts_postprocess():
                    final_path = tts_path
                    final_duration = tts_duration
                else:
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
            self._queue_pending_audio(absolute_start, final_duration, final_path, original, translated)
            self._remember_scheduled_text(original, absolute_start)

        with self._state_lock:
            self._pending_audio.sort(key=lambda item: item[0])
            self._prepared_segments += 1

    def _process_subtitle_segment(self, start_seconds: float, tts_suffix: str) -> None:
        if self._temp_dir is None:
            return
        start_seconds = max(0.0, _finite_seconds(start_seconds, 0.0))
        self._emit_status("worker_ocr_subtitle_at", time=_format_hhmmss(start_seconds))
        subtitle_segments = recognize_hard_subtitles(
            self._video_path,
            start_seconds,
            self._segment_seconds(),
            self._temp_dir,
            self._config.source_language,
            config=self._config,
        )
        if not subtitle_segments:
            with self._state_lock:
                self._prepared_segments += 1
            return

        for index, subtitle_segment in enumerate(subtitle_segments):
            if self._stop_requested:
                return
            original = self._clean_transcript_text(
                _clean_worker_text(getattr(subtitle_segment, "text", "")),
                self._selected_whisper_language(),
            )
            absolute_start = max(0.0, _finite_seconds(getattr(subtitle_segment, "start", 0.0), 0.0))
            if self._is_duplicate_nearby_text(original, absolute_start):
                continue
            subtitle_end = max(
                absolute_start + 0.5,
                _finite_seconds(getattr(subtitle_segment, "end", None), absolute_start + 0.5),
            )
            duration = max(0.5, subtitle_end - absolute_start)
            segment_ms = int(absolute_start * 1000)
            tts_path = self._temp_dir / f"vi-subtitle-{segment_ms}-{index}.{tts_suffix}"

            self._emit_status("worker_translating_subtitle_at", time=_format_hhmmss(absolute_start))
            translated = self._translator.translate(original, self._selected_whisper_language())
            self._emit_subtitle_ready(absolute_start, duration, original, translated)
            if _tts_disabled(self._config):
                self.segment_ready.emit(original, translated)
                self._remember_scheduled_text(original, absolute_start)
                continue
            tts_text = prepare_tts_text(translated, self._config.target_language)
            if not tts_text:
                self._queue_silent_audio(
                    absolute_start,
                    duration,
                    self._temp_dir / f"vi-subtitle-{segment_ms}-{index}-silence.wav",
                    original,
                    translated,
                )
                self._remember_scheduled_text(original, absolute_start)
                continue
            self._emit_status("worker_creating_target_voice_at", time=_format_hhmmss(absolute_start))
            self._tts_provider.synthesize(tts_text, tts_path, voice=self._config.tts_voice)
            tts_duration = audio_duration_seconds(tts_path)
            if is_pathological_tts_duration(tts_text, tts_duration, duration):
                self._queue_silent_audio(
                    absolute_start,
                    duration,
                    self._temp_dir / f"vi-subtitle-{segment_ms}-{index}-guard-silence.wav",
                    original,
                    translated,
                )
                self._remember_scheduled_text(original, absolute_start)
                continue
            if self._skip_tts_postprocess():
                final_path = tts_path
                final_duration = tts_duration
            else:
                final_path = self._trim_leading_silence(tts_path)
                final_duration = audio_duration_seconds(final_path)
            self._queue_pending_audio(
                absolute_start,
                max(final_duration, duration * 0.25),
                final_path,
                original,
                translated,
            )
            self._remember_scheduled_text(original, absolute_start)

        with self._state_lock:
            self._pending_audio.sort(key=lambda item: item[0])
            self._prepared_segments += 1

    def _is_duplicate_nearby_text(self, text: str, start_seconds: float) -> bool:
        key = _text_key(text)
        if not key:
            return False
        start_seconds = max(0.0, _finite_seconds(start_seconds, 0.0))
        window_seconds = max(30.0, self._segment_seconds() * 3.0)
        with self._state_lock:
            self._audio_schedule.prune_text_window(start_seconds, window_seconds)
            return any(
                abs(start_seconds - _finite_seconds(known_start, 0.0)) <= window_seconds
                and _text_keys_similar(known_key, key)
                for known_key, known_start in self._scheduled_text_keys
            )

    def _remember_scheduled_text(self, text: str, start_seconds: float) -> None:
        key = _text_key(text)
        start_seconds = max(0.0, _finite_seconds(start_seconds, 0.0))
        if key:
            with self._state_lock:
                self._audio_schedule.remember_text(key, start_seconds)

    def _extract_audio(self, start_seconds: float, wav_path: Path) -> None:
        if self._config.audio_source == "system":
            capture_system_audio(
                wav_path,
                self._segment_seconds(),
                device_name=self._config.capture_system_device,
                backend=self._config.capture_backend,
                language_id=self._config.gui_language,
            )
            return
        if self._config.audio_source == "microphone":
            capture_microphone_audio(
                wav_path,
                self._segment_seconds(),
                device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
                language_id=self._config.gui_language,
            )
            return
        if self._config.audio_source == "system_microphone":
            capture_system_microphone_audio(
                wav_path,
                self._segment_seconds(),
                system_device_name=self._config.capture_system_device,
                microphone_device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
                language_id=self._config.gui_language,
            )
            return

        if self._is_http_source(self._video_path) and is_telegram_web_progressive_url(self._video_path):
            raise RuntimeError(ui_text("video_error_telegram_web_progressive", self._config.gui_language))

        cached_source = self._cached_source_audio()
        if cached_source is not None:
            extract_audio_range(
                cached_source,
                start_seconds,
                self._segment_seconds(),
                wav_path,
                cancel_callback=self._is_stop_requested,
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
                str(self._segment_seconds()),
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
        try:
            self._run_segment_extract_ffmpeg(args)
        except subprocess.CalledProcessError:
            if not self._is_http_source(self._video_path):
                raise
            fallback_args = [
                "-reconnect",
                "1",
                "-reconnect_streamed",
                "1",
                "-reconnect_delay_max",
                "5",
                "-i",
                self._video_path,
                "-ss",
                f"{start_seconds:.3f}",
                "-t",
                str(self._segment_seconds()),
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
            self._run_segment_extract_ffmpeg(fallback_args)

    def _run_segment_extract_ffmpeg(self, args: list[object]) -> None:
        run_ffmpeg_cancelable(
            args,
            cancel_callback=self._is_stop_requested,
            loglevel="error",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _start_source_audio_cache(self) -> None:
        if self._temp_dir is None:
            return
        source_input = self._source_audio_cache_input()
        if source_input is None:
            return
        self._source_audio_cache_path = self._temp_dir / "source-cache-16k.wav"
        self._source_audio_cache_ready = False
        self._source_audio_cache_cancel = False
        self._source_audio_cache_thread = threading.Thread(
            target=self._build_source_audio_cache,
            args=(source_input, self._source_audio_cache_path),
            daemon=True,
        )
        self._source_audio_cache_thread.start()

    def _source_audio_cache_input(self) -> str | None:
        if self._config.audio_source != "original":
            return None
        source = str(self._video_path or "").strip()
        if not source:
            return None
        if self._is_http_source(source):
            parsed = urlparse(source)
            suffix = Path(parsed.path).suffix.lower()
            if parsed.scheme.lower() in {"http", "https"} and suffix in DIRECT_HTTP_SOURCE_CACHE_SUFFIXES:
                return source
            return None
        source_path = Path(source)
        if source_path.exists() and source_path.is_file():
            return str(source_path)
        return None

    def _build_source_audio_cache(self, source_path: str, cache_path: Path) -> None:
        temp_path = cache_path.with_suffix(".tmp.wav")
        try:
            with measure_stage("dubbing", "source_audio_cache"):
                input_args: list[object] = []
                if self._is_http_source(source_path):
                    input_args.extend(
                        [
                            "-reconnect",
                            "1",
                            "-reconnect_streamed",
                            "1",
                            "-reconnect_delay_max",
                            "5",
                        ]
                    )
                run_ffmpeg_cancelable(
                    [
                        *input_args,
                        "-i",
                        source_path,
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
                        temp_path,
                    ],
                    cancel_callback=self._source_audio_cache_cancelled,
                    loglevel="fatal",
                )
            if temp_path.exists() and temp_path.stat().st_size > 0 and not self._source_audio_cache_cancelled():
                temp_path.replace(cache_path)
                self._source_audio_cache_ready = True
        except Exception as exc:
            self._source_audio_cache_ready = False
            LOGGER.info("Source audio cache unavailable; segment extraction will use direct reads: %s", exc)
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)

    def _cached_source_audio(self) -> Path | None:
        path = self._source_audio_cache_path
        if self._source_audio_cache_ready and path is not None and path.exists() and path.stat().st_size > 0:
            return path
        return None

    def _stop_source_audio_cache(self) -> None:
        self._source_audio_cache_cancel = True
        thread = self._source_audio_cache_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._source_audio_cache_thread = None

    def _source_audio_cache_cancelled(self) -> bool:
        return self._stop_requested or self._source_audio_cache_cancel

    def _clean_transcript_text(self, text: str, source_language: str | None = None) -> str:
        clean_text = _clean_worker_text(text)
        if not clean_text:
            return clean_text
        if self._skip_realtime_local_cleanup():
            if not self._realtime_cleanup_skip_warned:
                self._realtime_cleanup_skip_warned = True
                self._emit_status("worker_skipping_realtime_local_cleanup")
            return clean_text
        if self._transcript_cleaner.enabled:
            self._emit_status("worker_cleaning_transcript")
        return self._transcript_cleaner.clean(clean_text, source_language)

    def _skip_realtime_local_cleanup(self) -> bool:
        if not self._transcript_cleaner.enabled:
            return False
        if str(self._config.transcript_cleanup_provider or "").strip().lower() != "local":
            return False
        return self._config.audio_source in {"original", "system", "microphone", "system_microphone", "subtitle"}

    def _needs_reference_audio(self) -> bool:
        return bool(self._config.dubbing_auto_voice_gender or self._config.dubbing_auto_match_audio)

    def _queue_pending_audio(
        self,
        source_start_seconds: float,
        duration_seconds: float,
        audio_path: Path,
        original: str,
        translated: str,
    ) -> None:
        source_start = max(0.0, _finite_seconds(source_start_seconds, 0.0))
        duration = max(0.05, _finite_seconds(duration_seconds, 0.05))
        with self._state_lock:
            self._audio_schedule.queue_audio(
                source_start_seconds=source_start,
                duration_seconds=duration,
                audio_path=audio_path,
                original=original,
                translated=translated,
                policy=self._config.dubbing_overlap_policy,
                force_avoid_overlap=self._config.audio_source == "document_editor",
            )

    def _emit_subtitle_ready(
        self,
        source_start_seconds: float,
        duration_seconds: float,
        original: str,
        translated: str,
    ) -> None:
        start = max(0.0, _finite_seconds(source_start_seconds, 0.0))
        duration = max(0.25, _finite_seconds(duration_seconds, self._segment_seconds()))
        with self._state_lock:
            if not self._audio_schedule.register_subtitle(start, _text_key(original)):
                return
        self.subtitle_ready.emit(start, duration, original, translated)

    def _queue_silent_audio(
        self,
        source_start_seconds: float,
        duration_seconds: float,
        audio_path: Path,
        original: str,
        translated: str,
    ) -> None:
        ffmpeg_make_silence(duration_seconds, audio_path)
        self._queue_pending_audio(source_start_seconds, duration_seconds, audio_path, original, translated)

    def _overlap_playback_enabled(self) -> bool:
        if self._config.audio_source == "document_editor":
            return False
        return normalize_overlap_policy(self._config.dubbing_overlap_policy) != OVERLAP_POLICY_AVOID_OVERLAP

    def _skip_tts_postprocess(self) -> bool:
        return (
            not self._config.dubbing_auto_match_audio
            and _int_value(self._config.dubbing_speed_percent, default=0) == 0
        )

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
        except Exception as exc:
            LOGGER.debug("Unable to trim leading silence from TTS output %s: %s", audio_path, exc)
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
            and not self._overlap_playback_enabled()
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
            self._request_resume(self._tr("worker_target_audio_caught_up"))

    def _launch_due_audio(self, current_seconds: float) -> bool:
        if not self._overlap_playback_enabled() and any(
            process.poll() is None for process in self._active_audio_processes
        ):
            return False

        if self._config.audio_source in {"transcript", "document_editor"}:
            with self._state_lock:
                if self._overlap_playback_enabled():
                    ready = sorted(
                        [
                            item
                            for item in self._pending_audio
                            if current_seconds >= item[0] - PLAYBACK_AUDIO_LEAD_SECONDS
                        ],
                        key=lambda item: item[0],
                    )
                else:
                    ready = sorted(self._pending_audio, key=lambda item: item[0])[:1]
        else:
            with self._state_lock:
                ready = sorted(
                    [item for item in self._pending_audio if current_seconds >= item[0] - PLAYBACK_AUDIO_LEAD_SECONDS],
                    key=lambda item: item[0],
                )
        if not ready:
            return False

        launched = False
        for selected in ready:
            with self._state_lock:
                if selected not in self._pending_audio:
                    continue
                self._pending_audio.remove(selected)
            _, display_start, audio_path, original, translated = selected
            self._emit_status("worker_playing_target_voice")
            self.audio_started.emit(display_start)
            self.segment_ready.emit(original, translated)
            command = [
                ffplay_executable(),
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-volume",
                str(_clamped_int(self._config.dubbing_voice_volume, default=100, minimum=0, maximum=100)),
                str(audio_path),
            ]
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._active_audio_processes.append(subprocess.Popen(command, startupinfo=startupinfo))
            launched = True
        return launched

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
            self._audio_schedule.reset()
        self._last_video_time = None
        self._last_wall_time = None
        self._sync_hold_requested = False


_terminate_process = terminate_process


def _unsupported_audio_source_message(value: str, language_id: str | None = None) -> str:
    label = str(value or ui_text("worker_unknown_source", language_id))
    supported = ", ".join(sorted(SUPPORTED_AUDIO_SOURCES))
    return ui_text("worker_unsupported_audio_source", language_id, source=label, supported=supported)


def _format_worker_exception(exc: Exception, max_length: int = 800) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        executable = _process_executable_name(exc.cmd)
        prefix = f"{executable} failed with exit code {exc.returncode}"
        detail = _compact_process_detail(exc.stderr or exc.output or "", max_length=max_length - len(prefix) - 2)
        message = f"{prefix}: {detail}" if detail else prefix
    else:
        message = _clean_message(exc)
    if len(message) > max_length:
        return f"{message[: max_length - 3]}..."
    return message


def _compact_process_detail(detail: object, *, max_length: int = 500) -> str:
    text = _clean_message(detail).replace("\r", "\n")
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
        return Path(command_parts[0]).name or command_parts[0]
    return str(command or "process")


def _text_key(value: object) -> str:
    text = _clean_worker_text(value).casefold()
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
