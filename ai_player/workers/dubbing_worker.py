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
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.config import PROJECT_ROOT, AppConfig
from ai_player.core.gpu import ctranslate2_cuda_available, cuda_runtime_files_available
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
    schedule_timeline_start,
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
    normalize_tts_provider,
    prepare_tts_text,
)
from ai_player.services.whisper_runtime import (
    SharedWhisperModel,
    get_shared_whisper_model,
    whisper_transcribe_kwargs,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type as shared_whisper_compute_type,
)

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
        self._pending_audio: list[PendingAudio] = []
        self._scheduled_audio_until = 0.0
        self._last_video_time: float | None = None
        self._last_wall_time: float | None = None
        self._scheduled_text_keys: list[tuple[str, float]] = []
        self._state_lock = threading.RLock()
        self._segment_executor: ThreadPoolExecutor | None = None
        self._segment_futures: dict[Future[None], float] = {}
        self._completed_segment_starts: set[int] = set()
        self._source_audio_cache_path: Path | None = None
        self._source_audio_cache_ready = False
        self._source_audio_cache_cancel = False
        self._source_audio_cache_thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_active_audio()

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
                current + self._config.dubbing_start_delay_seconds,
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
                        self._request_pause(self._tr("worker_pause_for_target_sync"))
                        time.sleep(0.05)
                        continue
                    self._launch_due_audio(current)
                    ready_ahead = self._covered_until - current
                    if not self._is_live_capture_source() and ready_ahead < self._required_ready_ahead_seconds():
                        self._buffering = True
                        self._request_pause(self._tr("worker_waiting_target_voice"))

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
            self._stop_source_audio_cache()
            self._cleanup_temp_dir()
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _is_live_capture_source(self) -> bool:
        return self._config.audio_source in {"system", "microphone", "system_microphone"}

    def _can_process_segments_async(self) -> bool:
        return self._config.audio_source in {"original", "subtitle"}

    def _run_transcript_source(self) -> None:
        entries = _load_transcript_entries(
            self._config.transcript_path,
            self._config.segment_seconds,
            self._config.gui_language,
        )
        if not entries:
            self._buffering = False
            self._request_resume(self._tr("worker_transcript_empty"))
            while not self._stop_requested:
                time.sleep(0.2)
            return
        current = self._get_time_ms() / 1000.0
        self._next_segment_start = max(0.0, current + self._config.dubbing_start_delay_seconds)
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
            self._request_resume(self._tr("worker_transcript_dubbing_ready"))
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

        self._emit_status("worker_translating_transcript_at", time=_format_hhmmss(entry.start))
        translated = self._translator.translate(original, self._selected_whisper_language())
        if _tts_disabled(self._config):
            self.segment_ready.emit(original, translated)
            with self._state_lock:
                self._scheduled_audio_until = max(
                    self._scheduled_audio_until,
                    entry.end if entry.end is not None else entry.start + self._config.segment_seconds,
                )
            return
        entry_end = entry.end if entry.end is not None else entry.start + self._config.segment_seconds
        duration = max(0.25, entry_end - entry.start)
        tts_text = prepare_tts_text(translated, self._config.target_language)
        if not tts_text:
            self._queue_silent_audio(
                entry.start,
                duration,
                tts_path.with_name(f"{tts_path.stem}-silence.wav"),
                original,
                translated,
            )
            return
        self._emit_status("worker_creating_target_voice_at", time=_format_hhmmss(entry.start))
        self._tts_provider.synthesize(tts_text, tts_path, voice=self._config.tts_voice)
        if is_pathological_tts_duration(tts_text, audio_duration_seconds(tts_path), duration):
            self._queue_silent_audio(
                entry.start,
                duration,
                tts_path.with_name(f"{tts_path.stem}-guard-silence.wav"),
                original,
                translated,
            )
            return
        final_path = tts_path if self._skip_tts_postprocess() else self._trim_leading_silence(tts_path)
        final_duration = audio_duration_seconds(final_path)
        self._queue_pending_audio(entry.start, final_duration, final_path, original, translated)

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
            self._pending_audio.clear()
            self._scheduled_text_keys.clear()
            self._completed_segment_starts.clear()
            self._scheduled_audio_until = self._next_segment_start
        self._last_video_time = self._next_segment_start
        self._last_wall_time = time.monotonic()
        self._voice_selector.reset()
        self._buffering = True
        self._request_pause(self._tr("worker_resyncing_target_voice"))

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
            self._covered_until += self._config.segment_seconds

    def _segment_worker_count(self) -> int:
        configured = os.getenv("AI_PLAYER_DUBBING_SEGMENT_WORKERS", "").strip()
        if configured:
            try:
                return max(1, min(8, int(configured)))
            except ValueError:
                pass
        cpu_count = os.cpu_count() or 2
        return max(1, min(4, cpu_count // 2, int(self._config.dubbing_lookahead_segments or 1)))

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
        try:
            return self._model.transcribe(str(wav_path), **kwargs)
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self._emit_status("worker_whisper_cpu_compute_fallback")
                self._switch_whisper_to_cpu(exc)
                return self._model.transcribe(str(wav_path), **kwargs)
            if self._whisper_device == "cpu":
                raise
            self._emit_status("worker_whisper_cublas_fallback")
            self._switch_whisper_to_cpu(exc)
            return self._model.transcribe(str(wav_path), **kwargs)

    def _resume_if_buffer_ready(self, current_seconds: float) -> None:
        ready_ahead = self._covered_until - current_seconds
        required_segments = self._config.dubbing_prebuffer_segments
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
        configured_ready_ahead = max(0.0, float(self._config.dubbing_min_ready_ahead_seconds))
        segment_ready_ahead = max(
            0.5,
            float(self._config.segment_seconds) * max(1, self._config.dubbing_prebuffer_segments),
        )
        return min(configured_ready_ahead, segment_ready_ahead)

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

        self._emit_status("worker_listening_segment_at", time=_format_hhmmss(start_seconds))
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
            needs_reference_audio = self._needs_reference_audio()

            self._emit_status("worker_translating_sentence_at", time=_format_hhmmss(absolute_start))
            with measure_stage("dubbing", "translate", start=f"{absolute_start:.3f}"):
                translated = self._translator.translate(original, info.language)
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
            if is_pathological_tts_duration(tts_text, audio_duration_seconds(tts_path), speech_duration):
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
        self._emit_status("worker_ocr_subtitle_at", time=_format_hhmmss(start_seconds))
        subtitle_segments = recognize_hard_subtitles(
            self._video_path,
            start_seconds,
            self._config.segment_seconds,
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
            original = self._clean_transcript_text(subtitle_segment.text.strip(), self._selected_whisper_language())
            absolute_start = subtitle_segment.start
            if self._is_duplicate_nearby_text(original, absolute_start):
                continue
            duration = max(0.5, subtitle_segment.end - subtitle_segment.start)
            segment_ms = int(absolute_start * 1000)
            tts_path = self._temp_dir / f"vi-subtitle-{segment_ms}-{index}.{tts_suffix}"

            self._emit_status("worker_translating_subtitle_at", time=_format_hhmmss(absolute_start))
            translated = self._translator.translate(original, self._selected_whisper_language())
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
            if is_pathological_tts_duration(tts_text, audio_duration_seconds(tts_path), duration):
                self._queue_silent_audio(
                    absolute_start,
                    duration,
                    self._temp_dir / f"vi-subtitle-{segment_ms}-{index}-guard-silence.wav",
                    original,
                    translated,
                )
                self._remember_scheduled_text(original, absolute_start)
                continue
            final_path = tts_path if self._skip_tts_postprocess() else self._trim_leading_silence(tts_path)
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
                language_id=self._config.gui_language,
            )
            return
        if self._config.audio_source == "microphone":
            capture_microphone_audio(
                wav_path,
                self._config.segment_seconds,
                device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
                language_id=self._config.gui_language,
            )
            return
        if self._config.audio_source == "system_microphone":
            capture_system_microphone_audio(
                wav_path,
                self._config.segment_seconds,
                system_device_name=self._config.capture_system_device,
                microphone_device_name=self._config.capture_microphone_device,
                backend=self._config.capture_backend,
                language_id=self._config.gui_language,
            )
            return

        cached_source = self._cached_source_audio()
        if cached_source is not None:
            extract_audio_range(
                cached_source,
                start_seconds,
                self._config.segment_seconds,
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

    def _start_source_audio_cache(self) -> None:
        if self._temp_dir is None:
            return
        if self._config.audio_source != "original":
            return
        if self._is_http_source(self._video_path):
            return
        source_path = Path(self._video_path)
        if not source_path.exists() or not source_path.is_file():
            return
        self._source_audio_cache_path = self._temp_dir / "source-cache-16k.wav"
        self._source_audio_cache_ready = False
        self._source_audio_cache_cancel = False
        self._source_audio_cache_thread = threading.Thread(
            target=self._build_source_audio_cache,
            args=(source_path, self._source_audio_cache_path),
            daemon=True,
        )
        self._source_audio_cache_thread.start()

    def _build_source_audio_cache(self, source_path: Path, cache_path: Path) -> None:
        temp_path = cache_path.with_suffix(".tmp.wav")
        try:
            with measure_stage("dubbing", "source_audio_cache"):
                run_ffmpeg_cancelable(
                    [
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
        except Exception:
            self._source_audio_cache_ready = False
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

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
        return self._transcript_cleaner.clean(text, source_language)

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
        source_start = max(0.0, float(source_start_seconds))
        duration = max(0.05, float(duration_seconds or 0.0))
        with self._state_lock:
            scheduled_start, self._scheduled_audio_until = schedule_timeline_start(
                source_start_seconds=source_start,
                duration_seconds=duration,
                scheduled_until_seconds=self._scheduled_audio_until,
                policy=self._config.dubbing_overlap_policy,
                force_avoid_overlap=self._config.audio_source == "document_editor",
            )
            self._pending_audio.append((scheduled_start, source_start, audio_path, original, translated))
            self._pending_audio.sort(key=lambda item: item[0])

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
            str(self._config.performance_preset or "").strip().lower() == "low_latency"
            and not self._config.dubbing_auto_match_audio
            and int(self._config.dubbing_speed_percent or 0) == 0
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
                str(max(0, min(100, int(self._config.dubbing_voice_volume)))),
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


def _unsupported_audio_source_message(value: str, language_id: str | None = None) -> str:
    label = str(value or ui_text("worker_unknown_source", language_id))
    supported = ", ".join(sorted(SUPPORTED_AUDIO_SOURCES))
    return ui_text("worker_unsupported_audio_source", language_id, source=label, supported=supported)


def _tts_disabled(config: AppConfig) -> bool:
    return normalize_tts_provider(config.tts_provider) == "none"


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


def _segment_start_key(value: float) -> int:
    return int(round(float(value or 0.0) * 1000))


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
