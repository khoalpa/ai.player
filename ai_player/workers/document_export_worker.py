from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.app_logging import get_logger
from ai_player.core.config import AppConfig
from ai_player.core.i18n import ui_text
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.pipeline.export_plan import ExportCue, TranscriptCue
from ai_player.pipeline.export_plan import read_srt_cues as _read_srt_cues
from ai_player.pipeline.export_plan import timeline_mix_args as _timeline_mix_args
from ai_player.pipeline.export_plan import video_quality_settings as _video_quality_settings
from ai_player.services.document_reader import DocumentPage
from ai_player.services.ffmpeg import ProcessCancelled, run_ffmpeg_cancelable
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider
from ai_player.workers.aligned_audio import aligned_timeline_inputs
from ai_player.workers.document_export_voice import build_document_export_cue, build_prepared_document_export_cues
from ai_player.workers.export_media import (
    document_video_args,
    document_video_concat_lines,
    mux_document_video_args,
    silence_args,
    to_wav_args,
    trim_leading_silence_args,
)
from ai_player.workers.export_utils import (
    _clean_message,
    _duration_seconds,
    _export_worker_count,
    _json_text,
    _percent_value,
    _render_text_page_image,
    _translate_texts,
)
from ai_player.workers.worker_values import selected_source_language, voice_tts_suffix

LOGGER = get_logger(__name__)

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
                LOGGER.exception("Document review export worker failed.")
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
        return selected_source_language(self._config)

    def _build_audio_cues(self, transcript_cues: list[TranscriptCue]) -> list[ExportCue]:
        if self._temp_dir is None:
            return []
        tts_suffix = voice_tts_suffix(self._config)
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

        return build_prepared_document_export_cues(
            items=items,
            translated_items=translated_items,
            tts_suffix=tts_suffix,
            max_workers=_export_worker_count(),
            build_document_export_cue=self._build_document_export_cue,
            should_stop=lambda: self._stop_requested,
            set_range_progress=self._set_range_progress,
            emit_progress=self._emit_progress,
        )

    def _build_document_export_cue(
        self,
        index: int,
        cue: TranscriptCue,
        original: str,
        translated: str,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        return build_document_export_cue(
            index=index,
            cue=cue,
            original=original,
            translated=translated,
            tts_suffix=tts_suffix,
            temp_dir=self._temp_dir,
            config=self._config,
            tts_provider=self._tts_provider,
            tts_lock=self._tts_lock,
            make_silence=self._make_silence,
            trim_leading_silence=self._trim_leading_silence,
            to_wav=self._to_wav,
        )

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return
        timeline_inputs = aligned_timeline_inputs(
            cues,
            progress_start=76,
            progress_end=84,
            overlap_policy=self._config.dubbing_overlap_policy,
            force_avoid_overlap=False,
            should_abort=self._should_abort,
            set_range_progress=self._set_range_progress,
            timeline_audio_path=lambda _index, cue: cue.audio_path,
            duration_seconds=lambda cue, path: cue.duration_seconds or _duration_seconds(path),
        )
        if timeline_inputs is None:
            return

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
        concat_file = self._temp_dir / "document-video-concat.txt"
        concat_file.write_text(
            document_video_concat_lines(self._pages, image_paths, audio_duration_seconds),
            encoding="utf-8",
        )
        self._run_ffmpeg(
            document_video_args(concat_file, output_path, quality),
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
            mux_document_video_args(video_path, audio_path, self._output_path, quality),
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

    def _run_ffmpeg(self, args: list[object], *, respect_stop: bool = True, **kwargs) -> None:
        if respect_stop and self._stop_requested:
            raise RuntimeError(self._tr("export_error_cancelled"))
        cancel_callback = self._is_stop_requested if respect_stop else (lambda: False)
        run_ffmpeg_cancelable(args, cancel_callback=cancel_callback, **kwargs)

    def _is_stop_requested(self) -> bool:
        return self._stop_requested
