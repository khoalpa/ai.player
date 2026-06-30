from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.app_logging import get_logger
from ai_player.core.config import AppConfig
from ai_player.core.i18n import ui_text
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.core.runtime_errors import (
    ASR_RUNTIME_FAILED,
    EXPORT_OUTPUT_MISSING,
    FFMPEG_FAILED,
    MODEL_NOT_FOUND,
    TTS_PROVIDER_FAILED,
    CodedRuntimeError,
    coded_error_info,
    coded_user_message,
)
from ai_player.pipeline.export_plan import (
    ExportCue,
    ExportRange,
    TranscriptCue,
    VideoQualitySettings,
)
from ai_player.pipeline.export_plan import (
    cues_end_seconds as _cues_end_seconds,
)
from ai_player.pipeline.export_plan import (
    document_scale_filter as _document_scale_filter,
)
from ai_player.pipeline.export_plan import (
    parse_srt_time as _parse_srt_time,
)
from ai_player.pipeline.export_plan import (
    read_srt_cues as _read_srt_cues,
)
from ai_player.pipeline.export_plan import (
    scale_filter as _scale_filter,
)
from ai_player.pipeline.export_plan import (
    staged_background_voice_mix_args as _staged_background_voice_mix_args,
)
from ai_player.pipeline.export_plan import (
    timeline_mix_args as _timeline_mix_args,
)
from ai_player.pipeline.export_plan import (
    video_quality_settings as _video_quality_settings,
)
from ai_player.pipeline.export_plan import (
    write_srt_cues as _write_srt_cues,
)
from ai_player.pipeline.transcript_source import load_transcript_entries as _load_transcript_entries
from ai_player.services.asr import should_use_online_asr, transcribe_asr
from ai_player.services.audio_matcher import extract_audio_range, match_tts_to_reference
from ai_player.services.demucs_separation import (
    DemucsSeparationError,
    demucs_available,
    demucs_command,
)
from ai_player.services.ffmpeg import (
    ProcessCancelled,
    probe_duration_seconds,
    run_cancelable_process,
    run_ffmpeg_cancelable,
)
from ai_player.services.ffmpeg import make_silence as ffmpeg_make_silence
from ai_player.services.speaker_voice_selector import VoiceGenderSelector
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import TTSError, create_tts_provider
from ai_player.services.whisper_runtime import (
    SharedWhisperModel,
    get_shared_whisper_model,
    whisper_transcribe_kwargs,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type as shared_whisper_compute_type,
)
from ai_player.workers.aligned_audio import aligned_timeline_inputs, mix_timeline_inputs_chunked
from ai_player.workers.asr_fallback import transcribe_model_with_device_fallback
from ai_player.workers.document_export_worker import DocumentReviewExportWorker
from ai_player.workers.export_media import (
    extract_source_audio_args,
    full_quality_audio_args,
    mux_video_args,
    silence_args,
    to_wav_args,
    trim_leading_silence_args,
)
from ai_player.workers.export_utils import (
    _align_text_results,
    _clean_message,
    _clean_transcript_many,
    _duration_value,
    _effective_whisper_device,
    _export_worker_count,
    _ffmpeg_escape,
    _json_number,
    _json_text,
    _percent_value,
    _safe_float,
    _segment_export_items,
    _segments_words_payload,
    _to_wav,
    _transcript_export_items,
    _translate_texts,
    _trim_leading_silence,
    _tts_disabled,
    export_rejects_audio_source,
    export_requires_asr,
    export_uses_transcript_source,
)
from ai_player.workers.export_utils import (
    _source_cues_from_segments as _source_cues_from_segments_data,
)
from ai_player.workers.source_export_voice import (
    build_prepared_source_export_cues,
    build_source_export_cue,
    prepare_source_export_items,
    translate_export_items,
)
from ai_player.workers.staged_audio_stems import create_source_audio_stems
from ai_player.workers.staged_export_utils import (
    StagedExportPaths,
    prepare_staged_output_dir,
    staged_manifest_payload,
    write_staged_manifest,
)
from ai_player.workers.staged_target_voice import (
    build_target_voice_cue,
    build_target_voice_cues,
    target_voice_artifact_paths,
)
from ai_player.workers.transcript_export_voice import (
    build_prepared_transcript_export_cues,
    build_transcript_export_cue,
)
from ai_player.workers.worker_values import selected_source_language, voice_tts_suffix

LOGGER = get_logger(__name__)

__all__ = [
    "DocumentReviewExportWorker",
    "DubbingExportWorker",
    "DemucsSeparationError",
    "ExportCue",
    "ExportRange",
    "STAGED_EXPORT_STAGE_LABEL_KEYS",
    "STAGED_EXPORT_STAGES",
    "StagedDubbingExportWorker",
    "TranscriptCue",
    "VideoQualitySettings",
    "_document_scale_filter",
    "_parse_srt_time",
    "_read_srt_cues",
    "_scale_filter",
    "_staged_background_voice_mix_args",
    "_timeline_mix_args",
    "_video_quality_settings",
    "_align_text_results",
    "_clean_transcript_many",
    "_duration_seconds",
    "_ffmpeg_escape",
    "_json_number",
    "_json_text",
    "_make_silence",
    "_percent_value",
    "_probe_duration_seconds",
    "_safe_float",
    "_segments_words_payload",
    "_to_wav",
    "_translate_texts",
    "_trim_leading_silence",
]

STAGED_EXPORT_STAGES: tuple[str, ...] = (
    "source_audio_extracted",
    "source_transcribed",
    "target_subtitles_ready",
    "source_voice_filtered",
    "target_voice_segments_ready",
    "target_voice_aligned",
    "final_mix_ready",
    "dubbed_video_ready",
)

STAGED_EXPORT_STAGE_LABEL_KEYS: dict[str, str] = {
    "source_audio_extracted": "staged_export_stage_source_audio",
    "source_transcribed": "staged_export_stage_source_transcribed",
    "target_subtitles_ready": "staged_export_stage_target_subtitles",
    "source_voice_filtered": "staged_export_stage_source_voice_filtered",
    "target_voice_segments_ready": "staged_export_stage_target_voice_segments",
    "target_voice_aligned": "staged_export_stage_target_voice_aligned",
    "final_mix_ready": "staged_export_stage_final_mix",
    "dubbed_video_ready": "staged_export_stage_dubbed_video",
}

_STAGED_STAGE_INDEX = {stage: index for index, stage in enumerate(STAGED_EXPORT_STAGES)}


def _normalize_staged_stage(value: object, *, default: str) -> str:
    stage = str(value or "").strip()
    return stage if stage in _STAGED_STAGE_INDEX else default


def _staged_stage_index(stage: str) -> int:
    return _STAGED_STAGE_INDEX.get(stage, 0)


class DubbingExportWorker(QThread):
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
    partial_finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        video_path: str,
        output_path: str,
        export_kind: str,
        config: AppConfig,
        export_range: ExportRange | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._output_path = Path(output_path)
        self._export_kind = export_kind
        self._config = config
        self._export_range = export_range or ExportRange()
        self._stop_requested = False
        self._keep_partial_requested = False
        self._temp_dir: Path | None = None
        self._tts_provider = None
        self._translator = None
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._voice_selector = VoiceGenderSelector(self._config)
        self._tts_lock = threading.Lock()
        self._whisper_device = _effective_whisper_device(config.whisper_device)
        self._whisper_compute_type = shared_whisper_compute_type(config.whisper_compute_type, self._whisper_device)

    def stop(self, keep_partial: bool = False) -> None:
        if keep_partial:
            self._keep_partial_requested = True
        self._stop_requested = True

    def _tr(self, key: str, **kwargs: object) -> str:
        return ui_text(key, self._config.gui_language, **kwargs)

    def _emit_progress(self, key: str, **kwargs: object) -> None:
        self.progress_changed.emit(self._tr(key, **kwargs))

    def _should_abort(self) -> bool:
        return self._stop_requested and not self._keep_partial_requested

    def _set_progress(self, value: int) -> None:
        self.progress_percent.emit(_percent_value(value))

    def _set_range_progress(self, start: int, end: int, index: int, total: int) -> None:
        if total <= 0:
            self._set_progress(end)
            return
        ratio = max(0.0, min(1.0, (index + 1) / total))
        self._set_progress(round(start + (end - start) * ratio))

    def run(self) -> None:
        offline_env: OfflineEnvironmentToken | None = None
        try:
            offline_env = self._configure_offline_environment()
            self._voice_selector.reset()
            self._set_progress(0)
            self._emit_progress("export_progress_initializing")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = get_shared_vietnamese_translator(self._config)
            self._set_progress(8)
            if export_rejects_audio_source(self._config.audio_source):
                raise RuntimeError(self._tr("export_error_source_unsupported"))
            if export_requires_asr(self._config.audio_source):
                self._validate_whisper_model()
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-export-"))
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            if export_uses_transcript_source(self._config.audio_source):
                self._emit_progress("export_progress_reading_transcript")
                self._set_progress(12)
                cues = self._build_transcript_cues()
            else:
                self._emit_progress("export_progress_extracting_audio")
                self._set_progress(10)
                source_audio = self._temp_dir / "source.wav"
                self._extract_source_audio(source_audio)
                self._set_progress(18)

                self._emit_progress("export_progress_transcribing_translating")
                self._set_progress(22)
                cues = self._build_cues(source_audio)
            if self._should_abort():
                return
            if not cues:
                raise RuntimeError(self._tr("export_error_no_dialogue"))
            if self._keep_partial_requested:
                self._finalize_partial(cues)
                return

            self._emit_progress("export_progress_mixing_dubbed_audio")
            self._set_progress(76)
            dubbed_audio = self._temp_dir / "dubbed_vi.wav"
            self._build_aligned_audio(cues, dubbed_audio)
            self._set_progress(88)
            if self._should_abort():
                return

            if self._export_kind == "audio":
                self._set_progress(92)
                shutil.copyfile(dubbed_audio, self._output_path)
            elif self._export_kind == "video":
                self._emit_progress("export_progress_writing_mp4")
                self._set_progress(90)
                try:
                    self._mux_video(dubbed_audio, cancel_strategy="quit")
                except ProcessCancelled:
                    if self._keep_partial_requested and self._output_path.exists():
                        self.partial_finished.emit(str(self._output_path))
                    return
            else:
                raise RuntimeError(self._tr("export_error_invalid_kind", kind=self._export_kind))
            self._require_export_output(self._output_path)
            self._set_progress(100)
            self.export_finished.emit(str(self._output_path))
        except Exception as exc:
            if not self._stop_requested:
                self._log_worker_failure("Dubbing export worker failed.", exc)
                self.failed.emit(self._ui_failure_message(exc))
        finally:
            if self._tts_provider is not None:
                self._tts_provider.close()
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _configure_offline_environment(self) -> OfflineEnvironmentToken:
        return push_hf_offline_environment(
            self._config.whisper_offline or self._config.local_translation_offline or self._config.vieneu_tts_offline
        )

    def _validate_whisper_model(self) -> None:
        if should_use_online_asr(self._config, language=self._selected_whisper_language()):
            return
        if self._config.whisper_offline and not Path(self._config.whisper_model).exists():
            raise CodedRuntimeError(
                MODEL_NOT_FOUND,
                self._tr("export_error_missing_whisper_offline"),
                detail=f"Missing Whisper model path: {self._config.whisper_model}",
            )

    def _selected_whisper_language(self) -> str | None:
        return selected_source_language(self._config)

    def _build_transcript_cues(self) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        segment_seconds = _duration_value(self._config.segment_seconds, default=5.0, minimum=0.25)
        entries = _load_transcript_entries(
            self._config.transcript_path,
            segment_seconds,
            self._config.gui_language,
        )
        tts_suffix = voice_tts_suffix(self._config)
        items = _transcript_export_items(
            entries,
            segment_seconds=segment_seconds,
            export_range=self._export_range,
            cleaner=self._transcript_cleaner,
            source_language=self._selected_whisper_language(),
            should_abort=self._should_abort,
        )
        if not items:
            return []

        translated_items = translate_export_items(
            items=items,
            translator=self._translator,
            source_language=self._selected_whisper_language(),
            emit_segment=self.segment_ready.emit,
        )

        return build_prepared_transcript_export_cues(
            items=items,
            translated_items=translated_items,
            tts_suffix=tts_suffix,
            max_workers=_export_worker_count(),
            build_transcript_export_cue=self._build_transcript_export_cue,
            set_range_progress=self._set_range_progress,
            emit_progress=self._emit_progress,
        )

    def _build_transcript_export_cue(
        self,
        index: int,
        entry,
        original: str,
        translated: str,
        entry_start: float,
        entry_end: float,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        return build_transcript_export_cue(
            index=index,
            original=original,
            translated=translated,
            entry_start=entry_start,
            entry_end=entry_end,
            tts_suffix=tts_suffix,
            temp_dir=self._temp_dir,
            export_range=self._export_range,
            config=self._config,
            tts_provider=self._tts_provider,
            tts_lock=self._tts_lock,
            make_silence=self._make_silence,
            trim_leading_silence=self._trim_leading_silence,
            to_wav=self._to_wav,
        )

    def _extract_source_audio(self, output_path: Path) -> None:
        self._run_ffmpeg(extract_source_audio_args(self._video_path, output_path, self._export_range))

    def _build_cues(self, source_audio: Path) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        with measure_stage("export", "asr"):
            segments, info = self._transcribe_with_fallback(source_audio)
            segments = list(segments)
        self._set_progress(34)
        tts_suffix = voice_tts_suffix(self._config)
        source_language = _json_text(getattr(info, "language", None), default=None)
        items = _segment_export_items(
            segments,
            cleaner=self._transcript_cleaner,
            source_language=source_language,
            should_abort=self._should_abort,
        )
        if not items:
            return []

        translated_items = translate_export_items(
            items=items,
            translator=self._translator,
            source_language=source_language,
            emit_segment=self.segment_ready.emit,
        )

        prepared_items = prepare_source_export_items(
            items=items,
            source_audio=source_audio,
            temp_dir=self._temp_dir,
            config=self._config,
            voice_selector=self._voice_selector,
            extract_audio_range=extract_audio_range,
            should_stop=lambda: self._stop_requested,
            cancel_callback=self._is_stop_requested,
        )

        return build_prepared_source_export_cues(
            prepared_items=prepared_items,
            translated_items=translated_items,
            tts_suffix=tts_suffix,
            max_workers=_export_worker_count(),
            build_source_export_cue=self._build_source_export_cue,
            should_stop=lambda: self._stop_requested,
            set_range_progress=self._set_range_progress,
            emit_progress=self._emit_progress,
        )

    def _build_source_export_cue(
        self,
        index: int,
        original: str,
        translated: str,
        start_seconds: float,
        duration_seconds: float,
        reference_path: Path,
        voice: str,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        return build_source_export_cue(
            index=index,
            original=original,
            translated=translated,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            reference_path=reference_path,
            voice=voice,
            tts_suffix=tts_suffix,
            temp_dir=self._temp_dir,
            config=self._config,
            tts_provider=self._tts_provider,
            tts_lock=self._tts_lock,
            make_silence=self._make_silence,
            trim_leading_silence=self._trim_leading_silence,
            match_to_reference=match_tts_to_reference,
            cancel_callback=self._is_stop_requested,
        )

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
                self._emit_progress("worker_whisper_cpu_float16_fallback")
                try:
                    return self._switch_whisper_to_cpu(exc)
                except Exception as fallback_exc:
                    raise CodedRuntimeError(
                        ASR_RUNTIME_FAILED,
                        "ASR runtime failed. Check ASR model/device settings.",
                        detail=f"Whisper CPU fallback failed after {type(exc).__name__}: {fallback_exc}",
                    ) from fallback_exc
            if self._whisper_device == "cpu":
                raise CodedRuntimeError(
                    ASR_RUNTIME_FAILED,
                    "ASR runtime failed. Check ASR model/device settings.",
                    detail=f"Whisper model load failed: {exc}",
                ) from exc
            self._emit_progress("worker_whisper_cuda_fallback")
            try:
                return self._switch_whisper_to_cpu(exc)
            except Exception as fallback_exc:
                raise CodedRuntimeError(
                    ASR_RUNTIME_FAILED,
                    "ASR runtime failed. Check ASR model/device settings.",
                    detail=f"Whisper CUDA fallback failed after {type(exc).__name__}: {fallback_exc}",
                ) from fallback_exc

    def _switch_whisper_to_cpu(self, _cause: Exception | None = None) -> SharedWhisperModel:
        self._whisper_device = "cpu"
        self._whisper_compute_type = "int8"
        return get_shared_whisper_model(
            self._config.whisper_model,
            device=self._whisper_device,
            compute_type=self._whisper_compute_type,
            local_files_only=self._config.whisper_offline,
        )

    def _transcribe_with_fallback(self, source_audio: Path):
        language = self._selected_whisper_language()

        def transcribe_local():
            model = self._load_whisper_model()
            kwargs = whisper_transcribe_kwargs(self._config, language)
            return DubbingExportWorker._transcribe_model_with_fallback(self, model, source_audio, kwargs)

        return transcribe_asr(
            self._config,
            source_audio,
            language=language,
            local_transcriber=transcribe_local,
            cache_details={"word_timestamps": False},
        )

    def _transcribe_model_with_fallback(
        self,
        model: SharedWhisperModel,
        source_audio: Path,
        kwargs: dict[str, object],
        *,
        passthrough_errors: tuple[type[BaseException], ...] = (),
    ):
        try:
            return transcribe_model_with_device_fallback(
                model,
                source_audio,
                kwargs,
                whisper_device=lambda: self._whisper_device,
                whisper_compute_type=lambda: self._whisper_compute_type,
                emit_status=lambda key: self._emit_progress(key),
                switch_whisper_to_cpu=lambda exc: self._switch_whisper_to_cpu(exc),
                passthrough_errors=passthrough_errors,
            )
        except passthrough_errors:
            raise
        except Exception as exc:
            if isinstance(exc, CodedRuntimeError):
                raise
            raise CodedRuntimeError(
                ASR_RUNTIME_FAILED,
                "ASR runtime failed. Check ASR model/device settings.",
                detail=f"Whisper transcription failed for {source_audio}: {exc}",
            ) from exc

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return

        def timeline_audio_path(index: int, cue: ExportCue) -> Path:
            wav_path = self._temp_dir / f"cue-{index:05d}-pcm.wav"
            self._to_wav(cue.audio_path, wav_path)
            return wav_path

        timeline_inputs = aligned_timeline_inputs(
            cues,
            progress_start=76,
            progress_end=88,
            overlap_policy=self._config.dubbing_overlap_policy,
            force_avoid_overlap=self._config.audio_source == "document_editor",
            should_abort=self._should_abort,
            set_range_progress=self._set_range_progress,
            timeline_audio_path=timeline_audio_path,
            duration_seconds=lambda cue, path: cue.duration_seconds or self._duration_seconds(path),
        )
        if timeline_inputs is None:
            return

        if not timeline_inputs:
            self._make_silence(1.0, output_path)
            return

        mix_timeline_inputs_chunked(
            timeline_inputs,
            output_path,
            temp_dir=self._temp_dir,
            run_ffmpeg=lambda args: self._run_ffmpeg(args, respect_stop=not self._keep_partial_requested),
            timeline_mix_args=_timeline_mix_args,
        )

    def _make_silence(self, duration_seconds: float, output_path: Path) -> None:
        self._run_ffmpeg(silence_args(duration_seconds, output_path), respect_stop=not self._keep_partial_requested)

    def _to_wav(self, input_path: Path, output_path: Path) -> None:
        self._run_ffmpeg(to_wav_args(input_path, output_path), respect_stop=not self._keep_partial_requested)

    def _trim_leading_silence(self, audio_path: Path) -> Path:
        trimmed_path = audio_path.with_name(f"{audio_path.stem}-trimmed{audio_path.suffix}")
        try:
            self._run_ffmpeg(
                trim_leading_silence_args(audio_path, trimmed_path),
                check=False,
                respect_stop=not self._keep_partial_requested,
            )
        except Exception:
            return audio_path
        if trimmed_path.exists() and trimmed_path.stat().st_size > 0:
            return trimmed_path
        return audio_path

    @staticmethod
    def _duration_seconds(path: Path) -> float:
        return _probe_duration_seconds(path)

    def _mux_video(
        self,
        dubbed_audio: Path,
        *,
        output_path: Path | None = None,
        duration_seconds: float | None = None,
        cancel_strategy: str = "terminate",
        respect_stop: bool = True,
    ) -> None:
        quality = _video_quality_settings(self._config.export_video_quality)
        self._run_ffmpeg(
            mux_video_args(
                video_path=self._video_path,
                dubbed_audio=dubbed_audio,
                target_path=output_path or self._output_path,
                export_range=self._export_range,
                quality=quality,
                duration_seconds=duration_seconds,
            ),
            cancel_strategy=cancel_strategy,
            respect_stop=respect_stop,
        )

    def _finalize_partial(self, cues: list[ExportCue]) -> None:
        if self._temp_dir is None or not cues:
            return
        last_second = _cues_end_seconds(cues)
        if last_second <= 0.0:
            return
        self._emit_progress("export_progress_writing_partial")
        self._set_progress(90)
        dubbed_audio = self._temp_dir / "dubbed_vi_partial.wav"
        self._build_aligned_audio(cues, dubbed_audio)
        if self._export_kind == "audio":
            shutil.copyfile(dubbed_audio, self._output_path)
        elif self._export_kind == "video":
            self._mux_video(dubbed_audio, duration_seconds=last_second, respect_stop=False)
        else:
            return
        self.partial_finished.emit(str(self._output_path))

    def _run_ffmpeg(self, args: list[object], *, respect_stop: bool = True, **kwargs) -> None:
        if respect_stop and self._stop_requested:
            raise RuntimeError(self._tr("export_error_cancelled"))
        cancel_callback = self._is_stop_requested if respect_stop else (lambda: False)
        try:
            run_ffmpeg_cancelable(args, cancel_callback=cancel_callback, **kwargs)
        except ProcessCancelled:
            raise
        except subprocess.CalledProcessError as exc:
            raise CodedRuntimeError(
                FFMPEG_FAILED,
                "FFmpeg failed. Check source media and output path.",
                detail=_clean_message(exc),
            ) from exc

    def _require_export_output(self, path: Path) -> None:
        if path.exists() and path.stat().st_size > 0:
            return
        raise CodedRuntimeError(
            EXPORT_OUTPUT_MISSING,
            "Export output was not created. Check disk space and output path.",
            detail=f"Missing or empty export output: {path}",
        )

    def _ui_failure_message(self, exc: Exception) -> str:
        if isinstance(exc, TTSError):
            wrapped = CodedRuntimeError(
                TTS_PROVIDER_FAILED,
                "TTS provider failed. Check provider/model settings.",
                detail=exc,
            )
            return coded_user_message(wrapped)
        return coded_user_message(exc, fallback=_clean_message(exc))

    @staticmethod
    def _log_worker_failure(message: str, exc: Exception) -> None:
        info = coded_error_info(exc)
        if info is None:
            LOGGER.exception(message)
            return
        LOGGER.exception("%s code=%s detail=%s", message, info.code, info.detail)

    def _is_stop_requested(self) -> bool:
        return self._stop_requested


def _make_silence(duration_seconds: float, output_path: Path) -> None:
    ffmpeg_make_silence(_duration_value(duration_seconds, default=0.0), output_path)


def _duration_seconds(path: Path) -> float:
    return _probe_duration_seconds(path)


def _probe_duration_seconds(path: Path) -> float:
    return _duration_value(probe_duration_seconds(path), default=0.0)


class StagedDubbingExportWorker(DubbingExportWorker):
    def __init__(
        self,
        video_path: str,
        output_dir: str,
        config: AppConfig,
        export_range: ExportRange | None = None,
        start_stage: str | None = None,
        end_stage: str | None = None,
        force_stage: bool = True,
        artifact_overrides: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        output_root = Path(output_dir)
        normalized_overrides = self._normalize_artifact_overrides(artifact_overrides)
        video_source_path = normalized_overrides.get("source_video", Path(video_path))
        super().__init__(
            str(video_source_path),
            str(output_root / "dubbed_video.mp4"),
            "video",
            config,
            export_range,
            parent,
        )
        self._output_dir = output_root
        self._artifact_overrides = normalized_overrides
        self._paths = self._staged_paths_with_overrides(output_root, self._artifact_overrides)
        self._audio_dir = self._paths.audio_dir
        self._subtitle_dir = self._paths.subtitle_dir
        self._tts_dir = self._paths.tts_dir
        self._staged_manifest_stage = "initializing"
        self._start_stage = _normalize_staged_stage(start_stage, default=STAGED_EXPORT_STAGES[0])
        self._end_stage = _normalize_staged_stage(end_stage, default=STAGED_EXPORT_STAGES[-1])
        if _staged_stage_index(self._end_stage) < _staged_stage_index(self._start_stage):
            self._end_stage = self._start_stage
        self._force_stage = bool(force_stage)

    @staticmethod
    def _normalize_artifact_overrides(overrides: dict[str, str] | None) -> dict[str, Path]:
        allowed = {
            "source_full",
            "source_srt",
            "words_json",
            "target_srt",
            "source_voice",
            "background",
            "target_voice",
            "final_mix",
            "final_video",
            "tts_dir",
            "source_video",
        }
        normalized: dict[str, Path] = {}
        for key, value in (overrides or {}).items():
            if key not in allowed:
                continue
            text = str(value or "").strip()
            if text:
                normalized[key] = Path(text)
        return normalized

    @staticmethod
    def _staged_paths_with_overrides(output_dir: Path, overrides: dict[str, Path]) -> StagedExportPaths:
        paths = StagedExportPaths.from_output_dir(output_dir)
        path_overrides = {key: value for key, value in overrides.items() if key != "source_video"}
        if not path_overrides:
            return paths
        return replace(paths, **path_overrides)

    def run(self) -> None:
        offline_env: OfflineEnvironmentToken | None = None
        artifacts: dict[str, str] | None = None
        manifest_path: Path | None = None
        self._staged_manifest_stage = "initializing"
        separation_backend = ""
        try:
            previous_manifest = self._read_existing_staged_manifest()
            separation_backend = self._manifest_separation_backend(previous_manifest)
            offline_env = self._configure_offline_environment()
            self._voice_selector.reset()
            self._set_progress(0)
            self._emit_progress("staged_export_progress_initializing")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = get_shared_vietnamese_translator(self._config)
            if self._config.audio_source != "original":
                raise RuntimeError(self._tr("staged_export_error_source_unsupported"))
            if self._will_run_staged_stage("target_voice_segments_ready") and _tts_disabled(self._config):
                raise RuntimeError(self._tr("staged_export_error_tts_disabled"))
            if (
                self._config.dubbing_voice_volume <= 0
                and (
                    self._will_run_staged_stage("final_mix_ready")
                    or self._will_run_staged_stage("dubbed_video_ready")
                )
            ):
                raise RuntimeError(self._tr("staged_export_error_voice_volume_muted"))
            if self._will_run_staged_stage("source_transcribed"):
                self._validate_whisper_model()

            paths = self._paths
            self._temp_dir = paths.work_dir
            manifest_path = paths.manifest
            self._prepare_staged_output_dir(paths.final_video, paths.manifest)
            artifacts = paths.artifacts()
            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="running",
                stage="initialized",
            )
            self._staged_manifest_stage = "initialized"

            source_cues: list[TranscriptCue] | None = None
            target_cues: list[TranscriptCue] | None = None
            audio_cues: list[ExportCue] | None = None

            if self._will_run_staged_stage("source_audio_extracted"):
                self._emit_progress("staged_export_progress_extracting_audio")
                self._set_progress(8)
                self._extract_full_quality_audio(paths.source_full)
                if self._checkpoint_staged_stage(manifest_path, artifacts, "source_audio_extracted"):
                    return
            elif self._will_run_staged_stage("source_transcribed") or self._will_run_staged_stage(
                "source_voice_filtered"
            ):
                self._require_staged_artifact(paths.source_full)

            source_language: str | None = None
            if self._will_run_staged_stage("source_transcribed"):
                self._emit_progress("staged_export_progress_transcribing")
                self._set_progress(18)
                segments, info = self._transcribe_staged(paths.source_full)
                segments = list(segments)
                source_language = _json_text(getattr(info, "language", None), default=None)
                source_cues = self._source_cues_from_segments(segments, source_language)
                _write_srt_cues(paths.source_srt, source_cues)
                paths.words_json.write_text(
                    json.dumps(_segments_words_payload(segments, info), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if not source_cues:
                    raise RuntimeError(self._tr("export_error_no_dialogue"))
                if self._checkpoint_staged_stage(manifest_path, artifacts, "source_transcribed"):
                    return
            elif (
                self._will_run_staged_stage("target_subtitles_ready")
                or self._will_run_staged_stage("target_voice_segments_ready")
                or self._will_run_staged_stage("target_voice_aligned")
            ):
                source_cues = self._load_staged_cues(paths.source_srt)

            if self._will_run_staged_stage("target_subtitles_ready"):
                assert source_cues is not None
                self._emit_progress("staged_export_progress_translating")
                self._set_progress(34)
                target_cues = self._translate_source_cues(source_cues, source_language)
                _write_srt_cues(paths.target_srt, target_cues)
                if self._checkpoint_staged_stage(manifest_path, artifacts, "target_subtitles_ready"):
                    return
            elif (
                self._will_run_staged_stage("target_voice_segments_ready")
                or self._will_run_staged_stage("target_voice_aligned")
            ):
                target_cues = self._load_staged_cues(paths.target_srt)

            if self._will_run_staged_stage("source_voice_filtered"):
                self._emit_progress("staged_export_progress_filtering_source")
                self._set_progress(48)
                separation_backend = self._create_source_audio_stems(
                    paths.source_full,
                    paths.background,
                    paths.source_voice,
                )
                if self._checkpoint_staged_stage(
                    manifest_path,
                    artifacts,
                    "source_voice_filtered",
                    separation_backend=separation_backend,
                ):
                    return
            else:
                if self._will_run_staged_stage("target_voice_segments_ready"):
                    self._require_staged_artifact(paths.source_voice)
                if self._will_run_staged_stage("final_mix_ready"):
                    self._require_staged_artifact(paths.background)

            if self._will_run_staged_stage("target_voice_segments_ready"):
                assert source_cues is not None
                assert target_cues is not None
                self._emit_progress("staged_export_progress_creating_voice")
                self._set_progress(62)
                audio_cues = self._build_target_voice_cues(paths.source_voice, source_cues, target_cues)
                if self._checkpoint_staged_stage(
                    manifest_path,
                    artifacts,
                    "target_voice_segments_ready",
                    separation_backend=separation_backend,
                ):
                    return
            elif self._will_run_staged_stage("target_voice_aligned"):
                if source_cues is None:
                    source_cues = self._load_staged_cues(paths.source_srt)
                if target_cues is None:
                    target_cues = self._load_staged_cues(paths.target_srt)
                audio_cues = self._load_target_voice_export_cues(source_cues, target_cues)

            if self._will_run_staged_stage("target_voice_aligned"):
                assert audio_cues is not None
                self._emit_progress("staged_export_progress_aligning_voice")
                self._set_progress(78)
                self._build_aligned_audio(audio_cues, paths.target_voice)
                if self._checkpoint_staged_stage(
                    manifest_path,
                    artifacts,
                    "target_voice_aligned",
                    separation_backend=separation_backend,
                ):
                    return
            elif self._will_run_staged_stage("final_mix_ready"):
                self._require_staged_artifact(paths.target_voice)

            if self._will_run_staged_stage("final_mix_ready"):
                self._emit_progress("staged_export_progress_mixing_final")
                self._set_progress(88)
                self._mix_staged_final_audio(paths)
                if self._checkpoint_staged_stage(
                    manifest_path,
                    artifacts,
                    "final_mix_ready",
                    separation_backend=separation_backend,
                ):
                    return
            elif self._will_run_staged_stage("dubbed_video_ready"):
                self._ensure_staged_final_mix_for_mux(paths)

            if self._will_run_staged_stage("dubbed_video_ready"):
                self._emit_progress("staged_export_progress_writing_mp4")
                self._set_progress(94)
                self._mux_video(paths.final_mix, output_path=paths.final_video, cancel_strategy="quit")
                self._require_export_output(paths.final_video)

                self._write_staged_manifest(
                    manifest_path,
                    artifacts,
                    status="complete",
                    stage="dubbed_video_ready",
                    separation_backend=separation_backend,
                )
                self._staged_manifest_stage = "dubbed_video_ready"
                self._set_progress(100)
                self.export_finished.emit(str(self._output_dir))
        except ProcessCancelled:
            if self._keep_partial_requested:
                self._write_staged_terminal_status(manifest_path, artifacts, "partial", separation_backend)
                self.partial_finished.emit(str(self._output_dir))
            else:
                self._write_staged_terminal_status(manifest_path, artifacts, "cancelled", separation_backend)
        except Exception as exc:
            if self._stop_requested:
                status = "partial" if self._keep_partial_requested else "cancelled"
                self._write_staged_terminal_status(manifest_path, artifacts, status, separation_backend)
                if self._keep_partial_requested:
                    self.partial_finished.emit(str(self._output_dir))
            else:
                self._log_worker_failure("Staged dubbing export worker failed.", exc)
                self.failed.emit(self._ui_failure_message(exc))
        finally:
            if self._tts_provider is not None:
                self._tts_provider.close()
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _prepare_staged_output_dir(self, final_video: Path, manifest_path: Path) -> None:
        managed_files = self._paths.managed_files
        if self._force_stage:
            managed_files = self._managed_files_from_stage(self._start_stage)
        elif self._start_stage != STAGED_EXPORT_STAGES[0]:
            managed_files = (self._paths.manifest,)
        prepare_staged_output_dir(
            self._output_dir,
            managed_dirs=self._paths.managed_dirs,
            managed_files=managed_files,
        )

    def _managed_files_from_stage(self, stage: str) -> tuple[Path, ...]:
        paths = self._paths
        by_stage: dict[str, tuple[Path, ...]] = {
            "source_audio_extracted": (
                paths.source_full,
                paths.source_srt,
                paths.words_json,
                paths.target_srt,
                paths.source_voice,
                paths.background,
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "source_transcribed": (
                paths.source_srt,
                paths.words_json,
                paths.target_srt,
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "target_subtitles_ready": (
                paths.target_srt,
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "source_voice_filtered": (
                paths.source_voice,
                paths.background,
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "target_voice_segments_ready": (
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "target_voice_aligned": (
                paths.target_voice,
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "final_mix_ready": (
                paths.final_mix,
                paths.final_video,
                paths.manifest,
            ),
            "dubbed_video_ready": (
                paths.final_video,
                paths.manifest,
            ),
        }
        return by_stage.get(stage, self._paths.managed_files)

    def _write_staged_manifest(
        self,
        manifest_path: Path,
        artifacts: dict[str, str],
        *,
        status: str,
        stage: str,
        separation_backend: str = "",
    ) -> None:
        payload = staged_manifest_payload(
            video_path=self._video_path,
            export_range=self._export_range,
            artifacts=artifacts,
            config=self._config,
            status=status,
            stage=stage,
            separation_backend=separation_backend,
        )
        payload["requested_stages"] = {
            "start": self._start_stage,
            "end": self._end_stage,
            "force": self._force_stage,
        }
        if self._artifact_overrides:
            payload["artifact_overrides"] = {
                key: str(path)
                for key, path in sorted(self._artifact_overrides.items())
            }
        if stage in _STAGED_STAGE_INDEX:
            stage_index = _staged_stage_index(stage)
            payload["completed_stages"] = list(STAGED_EXPORT_STAGES[: stage_index + 1])
        write_staged_manifest(manifest_path, payload)

    def _read_existing_staged_manifest(self) -> dict[str, object]:
        try:
            data = json.loads(self._paths.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _manifest_separation_backend(manifest: dict[str, object]) -> str:
        source_filter = manifest.get("source_voice_filter")
        if not isinstance(source_filter, dict):
            return ""
        return _json_text(source_filter.get("backend"), default="")

    def _will_run_staged_stage(self, stage: str) -> bool:
        index = _staged_stage_index(stage)
        return _staged_stage_index(self._start_stage) <= index <= _staged_stage_index(self._end_stage)

    def _load_staged_cues(self, path: Path) -> list[TranscriptCue]:
        self._require_staged_artifact(path)
        cues = _read_srt_cues(path)
        if not cues:
            raise RuntimeError(self._tr("export_error_no_dialogue"))
        return cues

    def _require_staged_artifact(self, path: Path) -> None:
        if not path.exists() or (path.is_file() and path.stat().st_size <= 0):
            raise CodedRuntimeError(
                EXPORT_OUTPUT_MISSING,
                self._tr("staged_export_error_missing_artifact", path=str(path)),
                detail=f"Missing or empty staged artifact: {path}",
            )

    def _mix_staged_final_audio(self, paths: StagedExportPaths) -> None:
        self._require_staged_artifact(paths.background)
        self._require_staged_artifact(paths.target_voice)
        self._run_ffmpeg(
            _staged_background_voice_mix_args(
                paths.background,
                paths.target_voice,
                paths.final_mix,
                voice_volume_percent=self._config.dubbing_voice_volume,
            )
        )

    def _ensure_staged_final_mix_for_mux(self, paths: StagedExportPaths) -> None:
        if self._staged_final_mix_needs_rebuild(paths):
            self._emit_progress("staged_export_progress_mixing_final")
            self._set_progress(88)
            self._mix_staged_final_audio(paths)
            return
        self._require_staged_artifact(paths.final_mix)

    def _staged_final_mix_needs_rebuild(self, paths: StagedExportPaths) -> bool:
        if not paths.final_mix.exists() or paths.final_mix.stat().st_size <= 0:
            return True
        source_paths = (paths.background, paths.target_voice)
        if not all(path.exists() and path.stat().st_size > 0 for path in source_paths):
            return False
        if self._start_stage == "dubbed_video_ready" and self._force_stage:
            return True
        final_mtime = paths.final_mix.stat().st_mtime
        return any(path.stat().st_mtime > final_mtime for path in source_paths)

    def _load_target_voice_export_cues(
        self,
        source_cues: list[TranscriptCue],
        target_cues: list[TranscriptCue],
    ) -> list[ExportCue]:
        tts_suffix = voice_tts_suffix(self._config)
        cues: list[ExportCue] = []
        for index, (source_cue, target_cue) in enumerate(zip(source_cues, target_cues, strict=False)):
            _, audio_path = target_voice_artifact_paths(self._tts_dir, index, tts_suffix)
            self._require_staged_artifact(audio_path)
            duration = _probe_duration_seconds(audio_path) or max(
                0.25,
                target_cue.end_seconds - target_cue.start_seconds,
            )
            cues.append(
                ExportCue(
                    start_seconds=target_cue.start_seconds,
                    original=source_cue.text,
                    translated=target_cue.text,
                    audio_path=audio_path,
                    duration_seconds=duration,
                )
            )
        if not cues:
            raise RuntimeError(self._tr("export_error_no_dialogue"))
        return cues

    def _write_staged_terminal_status(
        self,
        manifest_path: Path | None,
        artifacts: dict[str, str] | None,
        status: str,
        separation_backend: str,
    ) -> None:
        if manifest_path is None or artifacts is None:
            return
        self._write_staged_manifest(
            manifest_path,
            artifacts,
            status=status,
            stage=self._staged_manifest_stage,
            separation_backend=separation_backend,
        )

    def _checkpoint_staged_stage(
        self,
        manifest_path: Path,
        artifacts: dict[str, str],
        stage: str,
        *,
        separation_backend: str = "",
    ) -> bool:
        if self._stop_after_staged_checkpoint(
            manifest_path,
            artifacts,
            stage,
            separation_backend=separation_backend,
        ):
            return True
        self._staged_manifest_stage = stage
        if stage == self._end_stage:
            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="complete",
                stage=stage,
                separation_backend=separation_backend,
            )
            self._set_progress(100)
            self.export_finished.emit(str(self._output_dir))
            return True
        return False

    def _stop_after_staged_checkpoint(
        self,
        manifest_path: Path,
        artifacts: dict[str, str],
        stage: str,
        *,
        separation_backend: str = "",
    ) -> bool:
        if self._should_abort():
            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="cancelled",
                stage=stage,
                separation_backend=separation_backend,
            )
            return True
        self._write_staged_manifest(
            manifest_path,
            artifacts,
            status="running",
            stage=stage,
            separation_backend=separation_backend,
        )
        if self._stop_requested and self._keep_partial_requested:
            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="partial",
                stage=stage,
                separation_backend=separation_backend,
            )
            self.partial_finished.emit(str(self._output_dir))
            return True
        return False

    def _extract_full_quality_audio(self, output_path: Path) -> None:
        self._run_ffmpeg(full_quality_audio_args(self._video_path, output_path, self._export_range))

    def _transcribe_staged(self, source_audio: Path):
        language = self._selected_whisper_language()

        def transcribe_local():
            model = self._load_whisper_model()
            kwargs = whisper_transcribe_kwargs(self._config, language)
            kwargs["word_timestamps"] = True
            try:
                return DubbingExportWorker._transcribe_model_with_fallback(
                    self,
                    model,
                    source_audio,
                    kwargs,
                    passthrough_errors=(TypeError,),
                )
            except TypeError:
                kwargs.pop("word_timestamps", None)
                return DubbingExportWorker._transcribe_model_with_fallback(self, model, source_audio, kwargs)

        return transcribe_asr(
            self._config,
            source_audio,
            language=language,
            local_transcriber=transcribe_local,
            cache_details={"workflow": "staged_export", "word_timestamps": True},
        )

    def _source_cues_from_segments(self, segments: list[object], source_language: str | None) -> list[TranscriptCue]:
        return _source_cues_from_segments_data(segments, self._transcript_cleaner, source_language)

    def _translate_source_cues(
        self,
        source_cues: list[TranscriptCue],
        source_language: str | None,
    ) -> list[TranscriptCue]:
        with measure_stage("staged_export", "translate_batch", cues=len(source_cues)):
            translated_items = _translate_texts(self._translator, [cue.text for cue in source_cues], source_language)
        target_cues: list[TranscriptCue] = []
        for index, source_cue in enumerate(source_cues):
            target_text = translated_items[index]
            self.segment_ready.emit(source_cue.text, target_text)
            target_cues.append(TranscriptCue(source_cue.start_seconds, source_cue.end_seconds, target_text))
        return target_cues

    def _create_source_audio_stems(self, source_audio: Path, background_path: Path, voice_path: Path) -> str:
        return create_source_audio_stems(
            config=self._config,
            source_audio=source_audio,
            background_path=background_path,
            voice_path=voice_path,
            temp_dir=self._temp_dir,
            run_process=run_cancelable_process,
            run_ffmpeg=self._run_ffmpeg,
            to_wav=self._to_wav,
            cancel_callback=self._is_stop_requested,
            demucs_available=demucs_available,
            demucs_command=demucs_command,
            temp_missing_message=self._tr("document_export_error_temp_missing"),
        )

    def _build_target_voice_cues(
        self,
        source_voice: Path,
        source_cues: list[TranscriptCue],
        target_cues: list[TranscriptCue],
    ) -> list[ExportCue]:
        if self._temp_dir is None:
            return []
        return build_target_voice_cues(
            config=self._config,
            source_voice=source_voice,
            source_cues=source_cues,
            target_cues=target_cues,
            temp_dir=self._temp_dir,
            voice_selector=self._voice_selector,
            extract_audio_range=extract_audio_range,
            build_target_voice_cue=self._build_target_voice_cue,
            probe_duration=_probe_duration_seconds,
            should_stop=lambda: self._stop_requested,
            set_range_progress=self._set_range_progress,
            emit_progress=self._emit_progress,
            cancel_callback=self._is_stop_requested,
        )

    def _build_target_voice_cue(
        self,
        index: int,
        target_cue: TranscriptCue,
        reference_path: Path,
        voice: str,
        tts_suffix: str,
    ) -> Path:
        return build_target_voice_cue(
            index=index,
            target_cue=target_cue,
            reference_path=reference_path,
            voice=voice,
            tts_suffix=tts_suffix,
            config=self._config,
            tts_dir=self._tts_dir,
            tts_provider=self._tts_provider,
            tts_lock=self._tts_lock,
            make_silence=self._make_silence,
            trim_leading_silence=self._trim_leading_silence,
            to_wav=self._to_wav,
            match_to_reference=match_tts_to_reference,
            cancel_callback=self._is_stop_requested,
        )
