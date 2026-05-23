from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.config import PROJECT_ROOT, AppConfig
from ai_player.core.gpu import ctranslate2_cuda_available, cuda_runtime_files_available
from ai_player.core.i18n import ui_text
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
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
    format_seconds_arg as _format_seconds_arg,
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
from ai_player.services.audio_matcher import extract_audio_range, match_tts_to_reference
from ai_player.services.audio_timeline import schedule_timeline_start
from ai_player.services.demucs_separation import DemucsSeparationError, demucs_available, demucs_command
from ai_player.services.document_reader import DocumentPage
from ai_player.services.ffmpeg import (
    ProcessCancelled,
    concat_escape,
    concat_file_line,
    probe_duration_seconds,
    run_cancelable_process,
    run_ffmpeg_cancelable,
    safe_float,
)
from ai_player.services.ffmpeg import (
    make_silence as ffmpeg_make_silence,
)
from ai_player.services.ffmpeg import (
    to_wav as ffmpeg_to_wav,
)
from ai_player.services.ffmpeg import (
    trim_leading_silence as ffmpeg_trim_leading_silence,
)
from ai_player.services.source_voice_filter import (
    normalize_source_voice_filter_mode,
    normalize_source_voice_filter_model,
)
from ai_player.services.speaker_voice_selector import VoiceGenderSelector
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider, is_non_speech_tts_text, normalize_tts_provider
from ai_player.services.whisper_runtime import (
    SharedWhisperModel,
    get_shared_whisper_model,
    whisper_transcribe_kwargs,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type as shared_whisper_compute_type,
)

__all__ = [
    "DocumentReviewExportWorker",
    "DubbingExportWorker",
    "ExportCue",
    "ExportRange",
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
]


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
            if self._config.audio_source in {"system", "microphone", "system_microphone", "subtitle"}:
                raise RuntimeError(self._tr("export_error_source_unsupported"))
            if self._config.audio_source not in {"transcript", "document_editor"}:
                self._validate_whisper_model()
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-export-"))
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            if self._config.audio_source in {"transcript", "document_editor"}:
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
            self._set_progress(100)
            self.export_finished.emit(str(self._output_path))
        except Exception as exc:
            if not self._stop_requested:
                self.failed.emit(_clean_message(exc))
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
        if self._config.whisper_offline and not Path(self._config.whisper_model).exists():
            raise RuntimeError(self._tr("export_error_missing_whisper_offline"))

    def _selected_whisper_language(self) -> str | None:
        language = str(self._config.source_language or "auto").strip().lower()
        return None if language in {"", "auto"} else language

    def _build_transcript_cues(self) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        segment_seconds = _duration_value(self._config.segment_seconds, default=5.0, minimum=0.25)
        entries = _load_transcript_entries(
            self._config.transcript_path,
            segment_seconds,
            self._config.gui_language,
        )
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        raw_items = []
        for index, entry in enumerate(entries):
            if self._should_abort():
                break
            entry_start, entry_end = _entry_time_bounds(entry, segment_seconds)
            if not self._export_range.overlaps(entry_start, entry_end):
                continue
            original = _json_text(getattr(entry, "text", ""), default="") or ""
            if not original:
                continue
            raw_items.append((index, entry, original, entry_start, entry_end))
        cleaned_items = _clean_transcript_many(
            self._transcript_cleaner,
            [item[2] for item in raw_items],
            self._selected_whisper_language(),
        )
        items = [
            (index, entry, original, entry_start, entry_end)
            for (index, entry, _raw, entry_start, entry_end), original in zip(raw_items, cleaned_items, strict=False)
            if original
        ]
        if not items:
            return []

        with measure_stage("export", "translate_batch", cues=len(items)):
            translated_items = _translate_texts(
                self._translator,
                [item[2] for item in items],
                self._selected_whisper_language(),
            )
        for (_index, _entry, original, _entry_start, _entry_end), translated in zip(
            items, translated_items, strict=False
        ):
            self.segment_ready.emit(original, translated)

        futures = []
        cues: list[ExportCue] = []
        with ThreadPoolExecutor(max_workers=_export_worker_count()) as executor:
            for item, translated in zip(items, translated_items, strict=False):
                futures.append(
                    executor.submit(
                        self._build_transcript_export_cue,
                        item[0],
                        item[1],
                        item[2],
                        translated,
                        item[3],
                        item[4],
                        tts_suffix,
                    )
                )
            total_entries = max(1, len(futures))
            for completed, future in enumerate(as_completed(futures)):
                cue = future.result()
                cues.append(cue)
                self._set_range_progress(18, 74, completed, total_entries)
                self._emit_progress("export_progress_creating_voice_at", time=_format_hhmmss(cue.start_seconds))
        return sorted(cues, key=lambda cue: cue.start_seconds)

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
        tts_path = self._temp_dir / f"transcript-cue-{index:05d}.{tts_suffix}"
        wav_path = self._temp_dir / f"transcript-cue-{index:05d}.wav"
        duration = max(0.25, entry_end - entry_start)
        if _tts_disabled(self._config) or is_non_speech_tts_text(translated):
            self._make_silence(duration, wav_path)
            return ExportCue(
                start_seconds=self._export_range.shift(entry_start),
                original=original,
                translated=translated,
                audio_path=wav_path,
                duration_seconds=duration,
            )
        with self._tts_lock:
            with measure_stage("export", "tts", cue=index):
                self._tts_provider.synthesize(translated, tts_path, voice=self._config.tts_voice)
        with measure_stage("export", "postprocess", cue=index):
            self._to_wav(self._trim_leading_silence(tts_path), wav_path)
            duration = _probe_duration_seconds(wav_path)
        return ExportCue(
            start_seconds=self._export_range.shift(entry_start),
            original=original,
            translated=translated,
            audio_path=wav_path,
            duration_seconds=duration,
        )

    def _extract_source_audio(self, output_path: Path) -> None:
        args: list[object] = []
        if self._export_range.start_seconds > 0.0:
            args.extend(["-ss", _format_seconds_arg(self._export_range.start_seconds)])
        args.extend(["-i", self._video_path])
        if self._export_range.duration_seconds is not None:
            args.extend(["-t", _format_seconds_arg(self._export_range.duration_seconds)])
        args.extend(["-vn", "-ac", "1", "-ar", "16000", "-y", str(output_path)])
        self._run_ffmpeg(args)

    def _build_cues(self, source_audio: Path) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        with measure_stage("export", "asr"):
            segments, info = self._transcribe_with_fallback(source_audio)
            segments = list(segments)
        self._set_progress(34)
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        raw_items = []
        source_language = _json_text(getattr(info, "language", None), default=None)
        for index, segment in enumerate(segments):
            if self._should_abort():
                break
            original = _json_text(getattr(segment, "text", ""), default="") or ""
            if not original:
                continue
            start_seconds = max(0.0, _json_number(getattr(segment, "start", 0.0), default=0.0) or 0.0)
            end_value = _json_number(getattr(segment, "end", None), default=None)
            end_seconds = max(start_seconds + 0.25, end_value if end_value is not None else start_seconds + 0.25)
            duration_seconds = max(0.25, end_seconds - start_seconds)
            raw_items.append((index, original, start_seconds, duration_seconds))
        cleaned_items = _clean_transcript_many(
            self._transcript_cleaner,
            [item[1] for item in raw_items],
            source_language,
        )
        items = [
            (index, original, start_seconds, duration_seconds)
            for (index, _raw, start_seconds, duration_seconds), original in zip(raw_items, cleaned_items, strict=False)
            if original
        ]
        if not items:
            return []

        with measure_stage("export", "translate_batch", cues=len(items)):
            translated_items = _translate_texts(self._translator, [item[1] for item in items], source_language)

        for (_index, original, _start_seconds, _duration_seconds), translated in zip(
            items, translated_items, strict=False
        ):
            self.segment_ready.emit(original, translated)

        prepared_items = []
        needs_reference_audio = _export_reference_audio_required(self._config)
        for index, original, start_seconds, duration_seconds in items:
            if self._stop_requested:
                break
            reference_path = self._temp_dir / f"cue-{index:05d}-ref.wav"
            if needs_reference_audio:
                with measure_stage("export", "reference", cue=index):
                    extract_audio_range(
                        source_audio,
                        start_seconds,
                        duration_seconds,
                        reference_path,
                        cancel_callback=self._is_stop_requested,
                    )
            else:
                reference_path = source_audio
            voice = self._config.tts_voice
            if self._config.dubbing_auto_voice_gender and not _tts_disabled(self._config):
                voice = self._voice_selector.select_voice(
                    reference_path,
                    provider=self._config.tts_provider,
                    config=self._config,
                ).voice
            prepared_items.append((index, original, start_seconds, duration_seconds, reference_path, voice))

        futures = []
        cues: list[ExportCue] = []
        max_workers = _export_worker_count()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for item, translated in zip(prepared_items, translated_items, strict=False):
                futures.append(
                    executor.submit(
                        self._build_source_export_cue,
                        item[0],
                        item[1],
                        translated,
                        item[2],
                        item[3],
                        item[4],
                        item[5],
                        tts_suffix,
                    )
                )
            total_segments = max(1, len(futures))
            for completed, future in enumerate(as_completed(futures)):
                if self._stop_requested:
                    break
                cue = future.result()
                cues.append(cue)
                self._set_range_progress(35, 74, completed, total_segments)
                self._emit_progress("export_progress_creating_voice_at", time=_format_hhmmss(cue.start_seconds))
        return sorted(cues, key=lambda cue: cue.start_seconds)

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
        tts_path = self._temp_dir / f"cue-{index:05d}.{tts_suffix}"
        matched_path = self._temp_dir / f"cue-{index:05d}-matched.wav"
        if _tts_disabled(self._config):
            return ExportCue(
                start_seconds=start_seconds,
                original=original,
                translated=translated,
                audio_path=reference_path,
                duration_seconds=duration_seconds,
            )
        if is_non_speech_tts_text(translated):
            self._make_silence(duration_seconds, matched_path)
            return ExportCue(
                start_seconds=start_seconds,
                original=original,
                translated=translated,
                audio_path=matched_path,
                duration_seconds=duration_seconds,
            )
        with self._tts_lock:
            with measure_stage("export", "tts", cue=index):
                self._tts_provider.synthesize(translated, tts_path, voice=voice)
        with measure_stage("export", "postprocess", cue=index):
            final_audio = match_tts_to_reference(
                reference_path=reference_path,
                tts_path=self._trim_leading_silence(tts_path),
                output_path=matched_path,
                target_duration_seconds=duration_seconds,
                config=self._config,
                cancel_callback=self._is_stop_requested,
            )
            final_duration = max(0.25, _probe_duration_seconds(final_audio) or duration_seconds)
        return ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=final_audio,
            duration_seconds=final_duration,
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
                return self._switch_whisper_to_cpu(exc)
            if self._whisper_device == "cpu":
                raise
            self._emit_progress("worker_whisper_cuda_fallback")
            return self._switch_whisper_to_cpu(exc)

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
        model = self._load_whisper_model()
        kwargs = whisper_transcribe_kwargs(self._config, self._selected_whisper_language())
        try:
            return model.transcribe(str(source_audio), **kwargs)
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self._emit_progress("worker_whisper_cpu_compute_fallback")
                model = self._switch_whisper_to_cpu(exc)
                return model.transcribe(str(source_audio), **kwargs)
            if self._whisper_device == "cpu":
                raise
            self._emit_progress("worker_whisper_cublas_fallback")
            model = self._switch_whisper_to_cpu(exc)
            return model.transcribe(str(source_audio), **kwargs)

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return

        timeline_inputs: list[tuple[Path, float]] = []
        scheduled_until = 0.0
        for index, cue in enumerate(sorted(cues, key=lambda item: item.start_seconds)):
            if self._should_abort():
                return
            self._set_range_progress(76, 88, index, len(cues))

            wav_path = self._temp_dir / f"cue-{index:05d}-pcm.wav"
            self._to_wav(cue.audio_path, wav_path)
            duration = cue.duration_seconds or self._duration_seconds(wav_path) or 0.25
            scheduled_start, scheduled_until = schedule_timeline_start(
                source_start_seconds=cue.start_seconds,
                duration_seconds=duration,
                scheduled_until_seconds=scheduled_until,
                policy=self._config.dubbing_overlap_policy,
                force_avoid_overlap=self._config.audio_source == "document_editor",
            )
            timeline_inputs.append((wav_path, scheduled_start))

        if not timeline_inputs:
            self._make_silence(1.0, output_path)
            return

        self._run_ffmpeg(
            _timeline_mix_args(timeline_inputs, output_path),
            respect_stop=not self._keep_partial_requested,
        )

    def _make_silence(self, duration_seconds: float, output_path: Path) -> None:
        duration = _duration_value(duration_seconds, default=0.0)
        self._run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            respect_stop=not self._keep_partial_requested,
        )

    def _to_wav(self, input_path: Path, output_path: Path) -> None:
        self._run_ffmpeg(
            [
                "-i",
                input_path,
                "-ar",
                44100,
                "-ac",
                2,
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            respect_stop=not self._keep_partial_requested,
        )

    def _trim_leading_silence(self, audio_path: Path) -> Path:
        trimmed_path = audio_path.with_name(f"{audio_path.stem}-trimmed{audio_path.suffix}")
        try:
            self._run_ffmpeg(
                [
                    "-i",
                    audio_path,
                    "-af",
                    "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB",
                    "-y",
                    trimmed_path,
                ],
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
        target_path = output_path or self._output_path
        command: list[object] = []
        if self._export_range.start_seconds > 0.0:
            command.extend(["-ss", _format_seconds_arg(self._export_range.start_seconds)])
        command.extend(["-i", self._video_path, "-i", str(dubbed_audio)])
        mux_duration = duration_seconds if duration_seconds is not None else self._export_range.duration_seconds
        if mux_duration is not None:
            command.extend(["-t", _format_seconds_arg(mux_duration)])
        command.extend(["-map", "0:v:0", "-map", "1:a:0"])
        if quality.copy_source_video:
            command.extend(["-c:v", "copy"])
        else:
            command.extend(
                [
                    "-vf",
                    _scale_filter(quality.width, quality.height),
                    "-c:v",
                    "libx264",
                    "-preset",
                    quality.preset,
                    "-crf",
                    str(quality.crf),
                ]
            )
        command.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                quality.audio_bitrate,
                "-movflags",
                "+faststart",
                "-shortest",
                "-y",
                str(target_path),
            ]
        )
        self._run_ffmpeg(command, cancel_strategy=cancel_strategy, respect_stop=respect_stop)

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
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback, **kwargs)

    def _is_stop_requested(self) -> bool:
        return self._stop_requested


class StagedDubbingExportWorker(DubbingExportWorker):
    def __init__(
        self,
        video_path: str,
        output_dir: str,
        config: AppConfig,
        export_range: ExportRange | None = None,
        parent=None,
    ) -> None:
        output_root = Path(output_dir)
        super().__init__(
            video_path,
            str(output_root / "dubbed_video.mp4"),
            "video",
            config,
            export_range,
            parent,
        )
        self._output_dir = output_root
        self._audio_dir = output_root / "audio"
        self._subtitle_dir = output_root / "subtitles"
        self._tts_dir = output_root / "tts"

    def run(self) -> None:
        offline_env: OfflineEnvironmentToken | None = None
        artifacts: dict[str, str] | None = None
        manifest_path: Path | None = None
        staged_manifest_stage = "initializing"
        separation_backend = ""
        try:
            offline_env = self._configure_offline_environment()
            self._voice_selector.reset()
            self._set_progress(0)
            self._emit_progress("staged_export_progress_initializing")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = get_shared_vietnamese_translator(self._config)
            if self._config.audio_source != "original":
                raise RuntimeError(self._tr("staged_export_error_source_unsupported"))
            self._validate_whisper_model()

            self._temp_dir = self._output_dir / ".work"
            source_full = self._audio_dir / "source_full.wav"
            source_srt = self._subtitle_dir / "source.srt"
            words_json = self._subtitle_dir / "source.words.json"
            target_srt = self._subtitle_dir / "target.srt"
            source_voice = self._audio_dir / "source_voice.wav"
            background = self._audio_dir / "background_no_voice.wav"
            target_voice = self._audio_dir / "target_voice.wav"
            final_mix = self._audio_dir / "final_mix.wav"
            final_video = self._output_dir / "dubbed_video.mp4"
            manifest_path = self._output_dir / "manifest.json"
            self._prepare_staged_output_dir(final_video, manifest_path)
            artifacts = self._staged_artifacts(
                source_full=source_full,
                source_srt=source_srt,
                words_json=words_json,
                target_srt=target_srt,
                source_voice=source_voice,
                background=background,
                target_voice=target_voice,
                final_mix=final_mix,
                final_video=final_video,
            )
            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="running",
                stage="initialized",
            )
            staged_manifest_stage = "initialized"

            self._emit_progress("staged_export_progress_extracting_audio")
            self._set_progress(8)
            self._extract_full_quality_audio(source_full)
            if self._stop_after_staged_checkpoint(manifest_path, artifacts, "source_audio_extracted"):
                return
            staged_manifest_stage = "source_audio_extracted"

            self._emit_progress("staged_export_progress_transcribing")
            self._set_progress(18)
            segments, info = self._transcribe_staged(source_full)
            segments = list(segments)
            source_cues = self._source_cues_from_segments(segments, getattr(info, "language", None))
            _write_srt_cues(source_srt, source_cues)
            words_json.write_text(
                json.dumps(_segments_words_payload(segments, info), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if not source_cues:
                raise RuntimeError(self._tr("export_error_no_dialogue"))
            if self._stop_after_staged_checkpoint(manifest_path, artifacts, "source_transcribed"):
                return
            staged_manifest_stage = "source_transcribed"

            self._emit_progress("staged_export_progress_translating")
            self._set_progress(34)
            target_cues = self._translate_source_cues(source_cues, getattr(info, "language", None))
            _write_srt_cues(target_srt, target_cues)
            if self._stop_after_staged_checkpoint(manifest_path, artifacts, "target_subtitles_ready"):
                return
            staged_manifest_stage = "target_subtitles_ready"

            self._emit_progress("staged_export_progress_filtering_source")
            self._set_progress(48)
            separation_backend = self._create_source_audio_stems(source_full, background, source_voice)
            if self._stop_after_staged_checkpoint(
                manifest_path,
                artifacts,
                "source_voice_filtered",
                separation_backend=separation_backend,
            ):
                return
            staged_manifest_stage = "source_voice_filtered"

            self._emit_progress("staged_export_progress_creating_voice")
            self._set_progress(62)
            audio_cues = self._build_target_voice_cues(source_voice, source_cues, target_cues)
            if self._stop_after_staged_checkpoint(
                manifest_path,
                artifacts,
                "target_voice_segments_ready",
                separation_backend=separation_backend,
            ):
                return
            staged_manifest_stage = "target_voice_segments_ready"

            self._emit_progress("staged_export_progress_aligning_voice")
            self._set_progress(78)
            self._build_aligned_audio(audio_cues, target_voice)
            if self._stop_after_staged_checkpoint(
                manifest_path,
                artifacts,
                "target_voice_aligned",
                separation_backend=separation_backend,
            ):
                return
            staged_manifest_stage = "target_voice_aligned"

            self._emit_progress("staged_export_progress_mixing_final")
            self._set_progress(88)
            self._run_ffmpeg(
                _staged_background_voice_mix_args(
                    background,
                    target_voice,
                    final_mix,
                    voice_volume_percent=self._config.dubbing_voice_volume,
                )
            )
            if self._stop_after_staged_checkpoint(
                manifest_path,
                artifacts,
                "final_mix_ready",
                separation_backend=separation_backend,
            ):
                return
            staged_manifest_stage = "final_mix_ready"

            self._emit_progress("staged_export_progress_writing_mp4")
            self._set_progress(94)
            self._mux_video(final_mix, output_path=final_video, cancel_strategy="quit")

            self._write_staged_manifest(
                manifest_path,
                artifacts,
                status="complete",
                stage="dubbed_video_ready",
                separation_backend=separation_backend,
            )
            self._set_progress(100)
            self.export_finished.emit(str(self._output_dir))
        except ProcessCancelled:
            if self._keep_partial_requested:
                if manifest_path is not None and artifacts is not None:
                    self._write_staged_manifest(
                        manifest_path,
                        artifacts,
                        status="partial",
                        stage=staged_manifest_stage,
                        separation_backend=separation_backend,
                    )
                self.partial_finished.emit(str(self._output_dir))
            elif manifest_path is not None and artifacts is not None:
                self._write_staged_manifest(
                    manifest_path,
                    artifacts,
                    status="cancelled",
                    stage=staged_manifest_stage,
                    separation_backend=separation_backend,
                )
        except Exception as exc:
            if self._stop_requested:
                if manifest_path is not None and artifacts is not None:
                    self._write_staged_manifest(
                        manifest_path,
                        artifacts,
                        status="partial" if self._keep_partial_requested else "cancelled",
                        stage=staged_manifest_stage,
                        separation_backend=separation_backend,
                    )
                if self._keep_partial_requested:
                    self.partial_finished.emit(str(self._output_dir))
            else:
                self.failed.emit(_clean_message(exc))
        finally:
            if self._tts_provider is not None:
                self._tts_provider.close()
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _prepare_staged_output_dir(self, final_video: Path, manifest_path: Path) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        for directory in (self._audio_dir, self._subtitle_dir, self._tts_dir, self._temp_dir):
            self._remove_managed_path(directory)
        for file_path in (final_video, manifest_path):
            self._remove_managed_path(file_path)
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        self._subtitle_dir.mkdir(parents=True, exist_ok=True)
        self._tts_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def _write_staged_manifest(
        self,
        manifest_path: Path,
        artifacts: dict[str, str],
        *,
        status: str,
        stage: str,
        separation_backend: str = "",
    ) -> None:
        manifest = {
            "version": 1,
            "status": _json_text(status, default=""),
            "stage": _json_text(stage, default=""),
            "source_video": _json_text(self._video_path, default=""),
            "range": {
                "start_seconds": _json_number(self._export_range.start_seconds, default=0.0),
                "end_seconds": _json_number(self._export_range.end_seconds, default=None),
            },
            "artifacts": artifacts,
            "source_voice_filter": {
                "enabled": bool(self._config.original_audio_voice_filter),
                "mode": normalize_source_voice_filter_mode(self._config.original_audio_voice_filter_mode),
                "model": normalize_source_voice_filter_model(self._config.original_audio_voice_filter_model),
                "backend": _json_text(separation_backend, default=""),
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    def _staged_artifacts(
        self,
        *,
        source_full: Path,
        source_srt: Path,
        words_json: Path,
        target_srt: Path,
        source_voice: Path,
        background: Path,
        target_voice: Path,
        final_mix: Path,
        final_video: Path,
    ) -> dict[str, str]:
        return {
            "source_full_wav": self._manifest_relative_path(source_full),
            "source_srt": self._manifest_relative_path(source_srt),
            "source_words_json": self._manifest_relative_path(words_json),
            "target_srt": self._manifest_relative_path(target_srt),
            "source_voice_wav": self._manifest_relative_path(source_voice),
            "background_no_voice_wav": self._manifest_relative_path(background),
            "target_voice_wav": self._manifest_relative_path(target_voice),
            "final_mix_wav": self._manifest_relative_path(final_mix),
            "dubbed_video_mp4": self._manifest_relative_path(final_video),
        }

    def _manifest_relative_path(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self._output_dir.resolve()).as_posix()

    def _remove_managed_path(self, path: Path) -> None:
        try:
            if path.parent.resolve() != self._output_dir.resolve():
                return
        except OSError:
            return
        if not path.exists() and not path.is_symlink():
            return
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

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
        args: list[object] = []
        if self._export_range.start_seconds > 0.0:
            args.extend(["-ss", _format_seconds_arg(self._export_range.start_seconds)])
        args.extend(["-i", self._video_path])
        if self._export_range.duration_seconds is not None:
            args.extend(["-t", _format_seconds_arg(self._export_range.duration_seconds)])
        args.extend(
            [
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(output_path),
            ]
        )
        self._run_ffmpeg(args)

    def _transcribe_staged(self, source_audio: Path):
        model = self._load_whisper_model()
        kwargs = whisper_transcribe_kwargs(self._config, self._selected_whisper_language())
        kwargs["word_timestamps"] = True
        try:
            return model.transcribe(str(source_audio), **kwargs)
        except TypeError:
            kwargs.pop("word_timestamps", None)
            return self._transcribe_staged_with_fallback(model, source_audio, kwargs)
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self._emit_progress("worker_whisper_cpu_compute_fallback")
                model = self._switch_whisper_to_cpu(exc)
                return model.transcribe(str(source_audio), **kwargs)
            if self._whisper_device == "cpu":
                raise
            self._emit_progress("worker_whisper_cublas_fallback")
            model = self._switch_whisper_to_cpu(exc)
            return model.transcribe(str(source_audio), **kwargs)

    def _transcribe_staged_with_fallback(
        self,
        model: SharedWhisperModel,
        source_audio: Path,
        kwargs: dict[str, object],
    ):
        try:
            return model.transcribe(str(source_audio), **kwargs)
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self._emit_progress("worker_whisper_cpu_compute_fallback")
                model = self._switch_whisper_to_cpu(exc)
                return model.transcribe(str(source_audio), **kwargs)
            if self._whisper_device == "cpu":
                raise
            self._emit_progress("worker_whisper_cublas_fallback")
            model = self._switch_whisper_to_cpu(exc)
            return model.transcribe(str(source_audio), **kwargs)

    def _source_cues_from_segments(self, segments: list[object], source_language: str | None) -> list[TranscriptCue]:
        raw_items: list[tuple[float, float, str]] = []
        for segment in segments:
            original = _json_text(getattr(segment, "text", ""), default="") or ""
            if not original:
                continue
            start_seconds = max(0.0, _json_number(getattr(segment, "start", 0.0), default=0.0) or 0.0)
            end_value = _json_number(getattr(segment, "end", None), default=None)
            end_seconds = max(start_seconds + 0.25, end_value if end_value is not None else start_seconds + 0.25)
            raw_items.append((start_seconds, end_seconds, original))
        cleaned = _clean_transcript_many(self._transcript_cleaner, [item[2] for item in raw_items], source_language)
        cues = []
        for (start_seconds, end_seconds, _raw), text in zip(raw_items, cleaned, strict=False):
            clean_text = _json_text(text, default="")
            if clean_text:
                cues.append(TranscriptCue(start_seconds, end_seconds, clean_text))
        return cues

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
        if not self._config.original_audio_voice_filter:
            shutil.copyfile(source_audio, background_path)
            shutil.copyfile(source_audio, voice_path)
            return "disabled"
        mode = normalize_source_voice_filter_mode(self._config.original_audio_voice_filter_mode)
        if mode == "ai":
            if not demucs_available():
                raise DemucsSeparationError("Demucs is not installed. Install the audio-separation extra first.")
            return self._create_demucs_stems(source_audio, background_path, voice_path)
        self._create_fast_stems(source_audio, background_path, voice_path)
        return "fast"

    def _create_demucs_stems(self, source_audio: Path, background_path: Path, voice_path: Path) -> str:
        if self._temp_dir is None:
            raise RuntimeError(self._tr("document_export_error_temp_missing"))
        model = normalize_source_voice_filter_model(self._config.original_audio_voice_filter_model)
        stems_dir = self._temp_dir / "demucs"
        run_cancelable_process(
            [
                *demucs_command(),
                "-n",
                model,
                "--two-stems",
                "vocals",
                "-o",
                str(stems_dir),
                str(source_audio),
            ],
            cancel_callback=self._is_stop_requested,
        )
        stem_root = stems_dir / model / source_audio.stem
        no_vocals = stem_root / "no_vocals.wav"
        vocals = stem_root / "vocals.wav"
        if not _nonempty_file(no_vocals):
            raise RuntimeError(f"Demucs did not create expected file: {no_vocals}")
        self._to_wav(no_vocals, background_path)
        if _nonempty_file(vocals):
            self._to_wav(vocals, voice_path)
        else:
            shutil.copyfile(source_audio, voice_path)
        return "ai"

    def _create_fast_stems(self, source_audio: Path, background_path: Path, voice_path: Path) -> None:
        self._run_ffmpeg(
            [
                "-i",
                source_audio,
                "-af",
                "aformat=channel_layouts=stereo,"
                "pan=stereo|c0=0.70*c0-0.55*c1|c1=0.70*c1-0.55*c0,"
                "volume=1.4,alimiter=limit=0.95",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                "-y",
                background_path,
            ]
        )
        self._run_ffmpeg(
            [
                "-i",
                source_audio,
                "-af",
                "aformat=channel_layouts=stereo,"
                "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1,"
                "alimiter=limit=0.95",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                "-y",
                voice_path,
            ]
        )

    def _build_target_voice_cues(
        self,
        source_voice: Path,
        source_cues: list[TranscriptCue],
        target_cues: list[TranscriptCue],
    ) -> list[ExportCue]:
        if self._temp_dir is None:
            return []
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        cues: list[ExportCue] = []
        total = max(1, len(target_cues))
        for index, (source_cue, target_cue) in enumerate(zip(source_cues, target_cues, strict=False)):
            if self._stop_requested:
                break
            self._set_range_progress(62, 78, index, total)
            duration = max(0.25, target_cue.end_seconds - target_cue.start_seconds)
            reference_path = self._temp_dir / f"reference-{index:05d}.wav"
            extract_audio_range(
                source_voice,
                target_cue.start_seconds,
                duration,
                reference_path,
                cancel_callback=self._is_stop_requested,
            )
            voice = self._config.tts_voice
            if self._config.dubbing_auto_voice_gender and not _tts_disabled(self._config):
                voice = self._voice_selector.select_voice(
                    reference_path,
                    provider=self._config.tts_provider,
                    config=self._config,
                ).voice
            audio_path = self._build_target_voice_cue(index, target_cue, reference_path, voice, tts_suffix)
            cues.append(
                ExportCue(
                    start_seconds=target_cue.start_seconds,
                    original=source_cue.text,
                    translated=target_cue.text,
                    audio_path=audio_path,
                    duration_seconds=_probe_duration_seconds(audio_path) or duration,
                )
            )
            self._emit_progress("export_progress_creating_voice_at", time=_format_hhmmss(target_cue.start_seconds))
        return cues

    def _build_target_voice_cue(
        self,
        index: int,
        target_cue: TranscriptCue,
        reference_path: Path,
        voice: str,
        tts_suffix: str,
    ) -> Path:
        duration = max(0.25, target_cue.end_seconds - target_cue.start_seconds)
        raw_path = self._tts_dir / f"{index + 1:04d}.{tts_suffix}"
        final_path = self._tts_dir / f"{index + 1:04d}-aligned.wav"
        if _tts_disabled(self._config) or not target_cue.text.strip() or is_non_speech_tts_text(target_cue.text):
            self._make_silence(duration, final_path)
            return final_path
        with self._tts_lock:
            with measure_stage("staged_export", "tts", cue=index):
                self._tts_provider.synthesize(target_cue.text, raw_path, voice=voice)
        with measure_stage("staged_export", "postprocess", cue=index):
            matched_path = match_tts_to_reference(
                reference_path=reference_path,
                tts_path=self._trim_leading_silence(raw_path),
                output_path=final_path,
                target_duration_seconds=duration,
                config=self._config,
                cancel_callback=self._is_stop_requested,
            )
        if matched_path != final_path:
            self._to_wav(matched_path, final_path)
        return final_path if final_path.exists() and final_path.stat().st_size > 0 else matched_path


class DocumentReviewExportWorker(QThread):
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
    partial_finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        transcript_path: str,
        pages: list[DocumentPage],
        output_path: str,
        config: AppConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._transcript_path = Path(transcript_path)
        self._pages = list(pages)
        self._output_path = Path(output_path)
        self._config = config
        self._stop_requested = False
        self._keep_partial_requested = False
        self._temp_dir: Path | None = None
        self._tts_provider = None
        self._translator = None
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._tts_lock = threading.Lock()

    def stop(self, keep_partial: bool = False) -> None:
        if keep_partial:
            self._keep_partial_requested = True
        self._stop_requested = True

    def _tr(self, key: str, **kwargs: object) -> str:
        return ui_text(key, self._config.gui_language, **kwargs)

    def _emit_progress(self, key: str, **kwargs: object) -> None:
        self.progress_changed.emit(self._tr(key, **kwargs))

    def _should_abort(self) -> bool:
        return self._stop_requested and not getattr(self, "_keep_partial_requested", False)

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
            self._set_progress(0)
            self._emit_progress("export_progress_initializing")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = get_shared_vietnamese_translator(self._config)
            self._set_progress(8)
            if not self._pages:
                raise RuntimeError(self._tr("document_export_error_no_pages"))
            if not self._transcript_path.exists():
                raise RuntimeError(self._tr("document_export_error_no_transcript"))

            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-document-export-"))
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            self._emit_progress("document_export_progress_reading_transcript")
            self._set_progress(12)
            transcript_cues = _read_srt_cues(self._transcript_path)
            if not transcript_cues:
                raise RuntimeError(self._tr("document_export_error_empty_transcript"))

            self._emit_progress("document_export_progress_translating_voice")
            self._set_progress(18)
            audio_cues = self._build_audio_cues(transcript_cues)
            if self._should_abort():
                return
            if self._keep_partial_requested:
                self._finalize_partial(audio_cues)
                return

            dubbed_audio = self._temp_dir / "document-dubbed.wav"
            self._emit_progress("document_export_progress_mixing_audio")
            self._set_progress(76)
            self._build_aligned_audio(audio_cues, dubbed_audio)
            self._set_progress(84)
            if self._should_abort():
                return
            audio_duration = _duration_seconds(dubbed_audio)

            self._emit_progress("document_export_progress_building_review_video")
            self._set_progress(86)
            review_video = self._temp_dir / "document-pages.mp4"
            self._build_document_video(review_video, audio_duration)

            self._emit_progress("document_export_progress_writing_mp4")
            self._set_progress(92)
            try:
                self._mux_document_video(review_video, dubbed_audio, cancel_strategy="quit")
            except ProcessCancelled:
                if self._keep_partial_requested and self._output_path.exists():
                    self.partial_finished.emit(str(self._output_path))
                return
            self._set_progress(100)
            self.export_finished.emit(str(self._output_path))
        except Exception as exc:
            if not self._stop_requested:
                self.failed.emit(_clean_message(exc))
        finally:
            if self._tts_provider is not None:
                self._tts_provider.close()
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            if offline_env is not None:
                pop_hf_offline_environment(offline_env)

    def _configure_offline_environment(self) -> OfflineEnvironmentToken:
        return push_hf_offline_environment(self._config.local_translation_offline or self._config.vieneu_tts_offline)

    def _selected_source_language(self) -> str | None:
        language = str(self._config.source_language or "auto").strip().lower()
        return None if language in {"", "auto"} else language

    def _build_audio_cues(self, transcript_cues: list[TranscriptCue]) -> list[ExportCue]:
        if self._temp_dir is None:
            return []
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        items = []
        for index, cue in enumerate(transcript_cues):
            if self._should_abort():
                break
            original = self._transcript_cleaner.clean(
                _json_text(getattr(cue, "text", ""), default="") or "",
                self._selected_source_language(),
            )
            if not original:
                continue
            items.append((index, cue, original))
        if not items:
            return []

        with measure_stage("document_export", "translate_batch", cues=len(items)):
            translated_items = _translate_texts(
                self._translator,
                [item[2] for item in items],
                self._selected_source_language(),
            )
        for (_index, _cue, original), translated in zip(items, translated_items, strict=False):
            self.segment_ready.emit(original, translated)

        cues: list[ExportCue] = []
        futures = []
        with ThreadPoolExecutor(max_workers=_export_worker_count()) as executor:
            for item, translated in zip(items, translated_items, strict=False):
                futures.append(
                    executor.submit(
                        self._build_document_export_cue,
                        item[0],
                        item[1],
                        item[2],
                        translated,
                        tts_suffix,
                    )
                )
            total_cues = max(1, len(futures))
            for completed, future in enumerate(as_completed(futures)):
                if self._stop_requested:
                    break
                cue = future.result()
                cues.append(cue)
                self._set_range_progress(18, 74, completed, total_cues)
                self._emit_progress(
                    "document_export_progress_creating_voice_at",
                    time=_format_hhmmss(cue.start_seconds),
                )
        return sorted(cues, key=lambda cue: cue.start_seconds)

    def _build_document_export_cue(
        self,
        index: int,
        cue: TranscriptCue,
        original: str,
        translated: str,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        tts_path = self._temp_dir / f"document-cue-{index:05d}.{tts_suffix}"
        wav_path = self._temp_dir / f"document-cue-{index:05d}.wav"
        cue_start, cue_end = _cue_time_bounds(cue)
        duration = max(0.25, cue_end - cue_start)
        if _tts_disabled(self._config) or is_non_speech_tts_text(translated):
            self._make_silence(duration, wav_path)
            return ExportCue(
                start_seconds=cue_start,
                original=original,
                translated=translated,
                audio_path=wav_path,
                duration_seconds=duration,
            )
        with self._tts_lock:
            with measure_stage("document_export", "tts", cue=index):
                self._tts_provider.synthesize(translated, tts_path, voice=self._config.tts_voice)
        with measure_stage("document_export", "postprocess", cue=index):
            self._to_wav(self._trim_leading_silence(tts_path), wav_path)
            duration = _probe_duration_seconds(wav_path)
        return ExportCue(
            start_seconds=cue_start,
            original=original,
            translated=translated,
            audio_path=wav_path,
            duration_seconds=duration,
        )

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return
        timeline_inputs: list[tuple[Path, float]] = []
        scheduled_until = 0.0
        for index, cue in enumerate(sorted(cues, key=lambda item: item.start_seconds)):
            if self._should_abort():
                return
            self._set_range_progress(76, 84, index, len(cues))
            duration = cue.duration_seconds or _duration_seconds(cue.audio_path) or 0.25
            scheduled_start, scheduled_until = schedule_timeline_start(
                source_start_seconds=cue.start_seconds,
                duration_seconds=duration,
                scheduled_until_seconds=scheduled_until,
                policy=self._config.dubbing_overlap_policy,
                force_avoid_overlap=False,
            )
            timeline_inputs.append((cue.audio_path, scheduled_start))

        if not timeline_inputs:
            self._make_silence(1.0, output_path)
            return

        self._run_ffmpeg(
            _timeline_mix_args(timeline_inputs, output_path, sample_rate=48000),
            respect_stop=not self._keep_partial_requested,
        )

    def _build_document_video(
        self,
        output_path: Path,
        audio_duration_seconds: float,
        *,
        respect_stop: bool = True,
    ) -> None:
        if self._temp_dir is None:
            return
        quality = _video_quality_settings(self._config.export_video_quality)
        image_paths = [self._page_image(page, index) for index, page in enumerate(self._pages, start=1)]
        total_page_duration = sum(
            _duration_value(page.duration_seconds, default=0.5, minimum=0.5) for page in self._pages
        )
        extra_duration = max(0.0, _duration_value(audio_duration_seconds, default=0.0) - total_page_duration)
        concat_file = self._temp_dir / "document-video-concat.txt"
        lines: list[str] = []
        for index, (page, image_path) in enumerate(zip(self._pages, image_paths, strict=True)):
            duration = _duration_value(page.duration_seconds, default=0.5, minimum=0.5)
            if index == len(self._pages) - 1:
                duration += extra_duration
            lines.append(concat_file_line(image_path))
            lines.append(f"duration {duration:.3f}\n")
        lines.append(concat_file_line(image_paths[-1]))
        concat_file.write_text("".join(lines), encoding="utf-8")
        self._run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-vf",
                _document_scale_filter(quality.width, quality.height),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                quality.preset,
                "-crf",
                str(quality.crf),
                "-y",
                str(output_path),
            ],
            respect_stop=respect_stop,
        )

    def _page_image(self, page: DocumentPage, index: int) -> Path:
        if page.image_path:
            candidate = Path(page.image_path)
            if candidate.exists():
                return candidate
        if self._temp_dir is None:
            raise RuntimeError(self._tr("document_export_error_temp_missing"))
        return _render_text_page_image(
            page.title or f"Trang {index}",
            page.text,
            self._temp_dir / f"document-page-{index:04d}.png",
        )

    def _mux_document_video(
        self,
        video_path: Path,
        audio_path: Path,
        *,
        cancel_strategy: str = "terminate",
        respect_stop: bool = True,
    ) -> None:
        quality = _video_quality_settings(self._config.export_video_quality)
        self._run_ffmpeg(
            [
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                quality.audio_bitrate,
                "-movflags",
                "+faststart",
                "-y",
                str(self._output_path),
            ],
            cancel_strategy=cancel_strategy,
            respect_stop=respect_stop,
        )

    def _finalize_partial(self, cues: list[ExportCue]) -> None:
        if self._temp_dir is None or not cues:
            return
        self._emit_progress("export_progress_writing_partial")
        self._set_progress(90)
        dubbed_audio = self._temp_dir / "document-dubbed-partial.wav"
        self._build_aligned_audio(cues, dubbed_audio)
        audio_duration = _duration_seconds(dubbed_audio)
        review_video = self._temp_dir / "document-pages-partial.mp4"
        self._build_document_video(review_video, audio_duration, respect_stop=False)
        self._mux_document_video(review_video, dubbed_audio, respect_stop=False)
        self.partial_finished.emit(str(self._output_path))

    def _make_silence(self, duration_seconds: float, output_path: Path) -> None:
        duration = _duration_value(duration_seconds, default=0.0)
        self._run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            respect_stop=not self._keep_partial_requested,
        )

    def _to_wav(self, input_path: Path, output_path: Path) -> None:
        self._run_ffmpeg(
            [
                "-i",
                input_path,
                "-ar",
                44100,
                "-ac",
                2,
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            respect_stop=not self._keep_partial_requested,
        )

    def _trim_leading_silence(self, audio_path: Path) -> Path:
        trimmed_path = audio_path.with_name(f"{audio_path.stem}-trimmed{audio_path.suffix}")
        try:
            self._run_ffmpeg(
                [
                    "-i",
                    audio_path,
                    "-af",
                    "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB",
                    "-y",
                    trimmed_path,
                ],
                check=False,
                respect_stop=not self._keep_partial_requested,
            )
        except Exception:
            return audio_path
        if trimmed_path.exists() and trimmed_path.stat().st_size > 0:
            return trimmed_path
        return audio_path

    def _run_ffmpeg(self, args: list[object], *, respect_stop: bool = True, **kwargs) -> None:
        if respect_stop and self._stop_requested:
            raise RuntimeError(self._tr("export_error_cancelled"))
        cancel_callback = self._is_stop_requested if respect_stop else (lambda: False)
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback, **kwargs)

    def _is_stop_requested(self) -> bool:
        return self._stop_requested


def _ffmpeg_escape(path: Path) -> str:
    return concat_escape(path)


def _make_silence(duration_seconds: float, output_path: Path) -> None:
    ffmpeg_make_silence(_duration_value(duration_seconds, default=0.0), output_path)


def _to_wav(input_path: Path, output_path: Path) -> None:
    ffmpeg_to_wav(input_path, output_path)


def _trim_leading_silence(audio_path: Path) -> Path:
    return ffmpeg_trim_leading_silence(audio_path)


def _duration_seconds(path: Path) -> float:
    return _probe_duration_seconds(path)


def _probe_duration_seconds(path: Path) -> float:
    return _duration_value(probe_duration_seconds(path), default=0.0)


def _safe_float(value: object) -> float | None:
    return safe_float(value)


def _duration_value(value: object, *, default: float, minimum: float = 0.0) -> float:
    number = _safe_float(value)
    if number is None or not math.isfinite(number):
        number = default
    return max(minimum, number)


def _percent_value(value: object) -> int:
    return max(0, min(100, int(round(_duration_value(value, default=0.0)))))


def _entry_time_bounds(entry: object, segment_seconds: float) -> tuple[float, float]:
    start_seconds = _duration_value(getattr(entry, "start", 0.0), default=0.0)
    fallback_end = start_seconds + max(0.25, segment_seconds)
    end_value = getattr(entry, "end", None)
    end_seconds = fallback_end if end_value is None else _duration_value(end_value, default=fallback_end)
    return start_seconds, max(start_seconds + 0.25, end_seconds)


def _cue_time_bounds(cue: object) -> tuple[float, float]:
    start_seconds = _duration_value(getattr(cue, "start_seconds", 0.0), default=0.0)
    end_seconds = _duration_value(getattr(cue, "end_seconds", None), default=start_seconds + 0.25)
    return start_seconds, max(start_seconds + 0.25, end_seconds)


def _nonempty_file(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _format_hhmmss(value: object) -> str:
    seconds_value = _safe_float(value) or 0.0
    total_seconds = max(0, int(seconds_value))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _render_text_page_image(title: str, text: str, output_path: Path) -> Path:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1920, 1080), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = _font(54, bold=True)
    body_font = _font(34)
    draw.rectangle((0, 0, 1919, 1079), outline="#d5dee8", width=4)
    draw.text((90, 72), title, fill="#0f172a", font=title_font)
    y = 170
    for line in _wrap_text(str(text or ""), body_font, 1700, draw)[:22]:
        draw.text((96, y), line, fill="#334155", font=body_font)
        y += 46
    image.save(output_path)
    return output_path


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in str(text or "").split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _segments_words_payload(
    segments: list[object],
    info: object,
) -> dict[str, object]:
    payload_segments: list[dict[str, object]] = []
    for segment in segments:
        words_payload: list[dict[str, object]] = []
        for word in getattr(segment, "words", None) or []:
            words_payload.append(
                {
                    "start": _json_number(getattr(word, "start", 0.0), default=0.0),
                    "end": _json_number(getattr(word, "end", 0.0), default=0.0),
                    "word": _json_text(getattr(word, "word", ""), default=""),
                    "probability": _json_number(getattr(word, "probability", 0.0), default=0.0),
                }
            )
        payload_segments.append(
            {
                "start": _json_number(getattr(segment, "start", 0.0), default=0.0),
                "end": _json_number(getattr(segment, "end", 0.0), default=0.0),
                "text": _json_text(getattr(segment, "text", ""), default=""),
                "words": words_payload,
            }
        )
    return {
        "language": _json_text(getattr(info, "language", None), default=None),
        "language_probability": _json_number(getattr(info, "language_probability", None), default=None),
        "segments": payload_segments,
    }


def _json_number(value: object, *, default: float | None) -> float | None:
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _json_text(value: object, *, default: str | None) -> str | None:
    if value is None:
        return default
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    text = " ".join(text.split())
    return text or default


def _clean_message(value: object) -> str:
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _clean_transcript_many(cleaner, texts: list[str], source_language: str | None) -> list[str]:
    fallback_texts = [_json_text(text, default="") or "" for text in texts]
    clean_many = getattr(cleaner, "clean_many", None)
    if callable(clean_many):
        return _align_text_results(fallback_texts, clean_many(texts, source_language))
    clean_one = getattr(cleaner, "clean", None)
    if callable(clean_one):
        return _align_text_results(fallback_texts, [clean_one(text, source_language) for text in texts])
    return fallback_texts


def _translate_texts(translator, texts: list[str], source_language: str | None) -> list[str]:
    fallback_texts = [_json_text(text, default="") or "" for text in texts]
    translate_many = getattr(translator, "translate_many", None)
    if callable(translate_many):
        return _align_text_results(fallback_texts, translate_many(fallback_texts, source_language))
    translate_one = getattr(translator, "translate", None)
    if callable(translate_one):
        return _align_text_results(fallback_texts, [translate_one(text, source_language) for text in fallback_texts])
    return fallback_texts


def _align_text_results(fallback_texts: list[str], results: object) -> list[str]:
    if isinstance(results, str | bytes):
        result_items = []
    else:
        try:
            result_items = list(results)
        except TypeError:
            result_items = []
    aligned: list[str] = []
    for index, fallback in enumerate(fallback_texts):
        cleaned = result_items[index] if index < len(result_items) else fallback
        if isinstance(cleaned, bytes):
            cleaned = cleaned.decode("utf-8", errors="replace")
        elif not isinstance(cleaned, str):
            cleaned = fallback
        cleaned_text = _json_text(cleaned, default="") or ""
        aligned.append(cleaned_text or fallback)
    return aligned


def _tts_disabled(config: AppConfig) -> bool:
    return normalize_tts_provider(config.tts_provider) == "none"


def _export_reference_audio_required(config: AppConfig) -> bool:
    return bool(_tts_disabled(config) or config.dubbing_auto_voice_gender or config.dubbing_auto_match_audio)


def _export_worker_count() -> int:
    configured = os.getenv("AI_PLAYER_EXPORT_WORKERS", "").strip()
    if configured:
        try:
            return max(1, min(16, int(configured)))
        except (OverflowError, ValueError):
            pass
    cpu_count = os.cpu_count() or 2
    return max(1, min(8, max(4, cpu_count // 2)))


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
