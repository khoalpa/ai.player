from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel
from PySide6.QtCore import QThread, Signal

from ai_player.core.config import PROJECT_ROOT, AppConfig
from ai_player.core.gpu import ctranslate2_cuda_available, cuda_runtime_files_available
from ai_player.core.offline_env import OfflineEnvironmentToken, pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.performance import measure_stage
from ai_player.services.audio_matcher import extract_audio_range, match_tts_to_reference, profile_reference_audio
from ai_player.services.document_reader import DocumentPage
from ai_player.services.ffmpeg import (
    concat_escape,
    concat_file_line,
    probe_duration_seconds,
    run_ffmpeg,
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
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation import VietnameseTranslator
from ai_player.services.tts import create_tts_provider, normalize_tts_provider, select_voice_for_gender
from ai_player.workers.dubbing_worker import _load_transcript_entries


@dataclass(frozen=True)
class ExportCue:
    start_seconds: float
    original: str
    translated: str
    audio_path: Path
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class TranscriptCue:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoQualitySettings:
    crf: int
    preset: str
    width: int
    height: int
    audio_bitrate: str
    copy_source_video: bool = False


class DubbingExportWorker(QThread):
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        video_path: str,
        output_path: str,
        export_kind: str,
        config: AppConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._output_path = Path(output_path)
        self._export_kind = export_kind
        self._config = config
        self._stop_requested = False
        self._temp_dir: Path | None = None
        self._tts_provider = None
        self._translator = None
        self._transcript_cleaner = TranscriptCleaner(self._config)
        self._tts_lock = threading.Lock()
        self._whisper_device = _effective_whisper_device(config.whisper_device)
        self._whisper_compute_type = config.whisper_compute_type
        self._tts_lock = threading.Lock()

    def stop(self) -> None:
        self._stop_requested = True

    def _set_progress(self, value: int) -> None:
        self.progress_percent.emit(max(0, min(100, int(value))))

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
            self.progress_changed.emit("Đang khởi tạo translator va TTS trong nền...")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = VietnameseTranslator(self._config)
            self._set_progress(8)
            if self._config.audio_source in {"system", "microphone", "system_microphone", "subtitle"}:
                raise RuntimeError(
                    "Export hiện hỗ trợ nguồn Âm gốc và Transcript. Nguồn live/Subtitle chỉ hỗ trợ lồng tiếng khi phát."
                )
            if self._config.audio_source not in {"transcript", "document_editor"}:
                self._validate_whisper_model()
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-export-"))
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            if self._config.audio_source in {"transcript", "document_editor"}:
                self.progress_changed.emit("Đang đọc transcript để export...")
                self._set_progress(12)
                cues = self._build_transcript_cues()
            else:
                self.progress_changed.emit("\u0110ang t\u00e1ch audio ngu\u1ed3n...")
                self._set_progress(10)
                source_audio = self._temp_dir / "source.wav"
                self._extract_full_audio(source_audio)
                self._set_progress(18)

                self.progress_changed.emit("\u0110ang nh\u1eadn di\u1ec7n v\u00e0 d\u1ecbch l\u1eddi tho\u1ea1i...")
                self._set_progress(22)
                cues = self._build_cues(source_audio)
            if self._stop_requested:
                return
            if not cues:
                raise RuntimeError("Kh\u00f4ng t\u00ecm th\u1ea5y l\u1eddi tho\u1ea1i \u0111\u1ec3 export.")

            self.progress_changed.emit("\u0110ang gh\u00e9p audio l\u1ed3ng ti\u1ebfng Vi\u1ec7t...")
            self._set_progress(76)
            dubbed_audio = self._temp_dir / "dubbed_vi.wav"
            self._build_aligned_audio(cues, dubbed_audio)
            self._set_progress(88)

            if self._export_kind == "audio":
                self._set_progress(92)
                shutil.copyfile(dubbed_audio, self._output_path)
            elif self._export_kind == "video":
                self.progress_changed.emit("\u0110ang xu\u1ea5t video MP4...")
                self._set_progress(90)
                self._mux_video(dubbed_audio)
            else:
                raise RuntimeError(f"Ki\u1ec3u export kh\u00f4ng h\u1ee3p l\u1ec7: {self._export_kind}")
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
            raise RuntimeError(
                "Thi\u1ebfu model Whisper offline. Ch\u1ea1y scripts\\download_offline_models.ps1 "
                "\u0111\u1ec3 t\u1ea3i model tr\u01b0\u1edbc khi export."
            )

    def _selected_whisper_language(self) -> str | None:
        language = str(self._config.source_language or "auto").strip().lower()
        return None if language in {"", "auto"} else language

    def _build_transcript_cues(self) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        entries = _load_transcript_entries(self._config.transcript_path, self._config.segment_seconds)
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        items = []

        for index, entry in enumerate(entries):
            if self._stop_requested:
                break
            original = self._transcript_cleaner.clean(entry.text.strip(), self._selected_whisper_language())
            if not original:
                continue
            items.append((index, entry, original))
        if not items:
            return []

        with measure_stage("export", "translate_batch", cues=len(items)):
            translated_items = self._translator.translate_many(
                [item[2] for item in items],
                self._selected_whisper_language(),
            )
        for (_index, _entry, original), translated in zip(items, translated_items, strict=False):
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
                        tts_suffix,
                    )
                )
            total_entries = max(1, len(futures))
            for completed, future in enumerate(as_completed(futures)):
                cue = future.result()
                cues.append(cue)
                self._set_range_progress(18, 74, completed, total_entries)
                self.progress_changed.emit(f"Dang tao giong Viet tai {_format_hhmmss(cue.start_seconds)}...")
        return sorted(cues, key=lambda cue: cue.start_seconds)

    def _build_transcript_export_cue(
        self,
        index: int,
        entry,
        original: str,
        translated: str,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        tts_path = self._temp_dir / f"transcript-cue-{index:05d}.{tts_suffix}"
        wav_path = self._temp_dir / f"transcript-cue-{index:05d}.wav"
        if _tts_disabled(self._config):
            duration = max(0.25, (entry.end or entry.start + self._config.segment_seconds) - entry.start)
            self._make_silence(duration, wav_path)
            return ExportCue(
                start_seconds=max(0.0, float(entry.start)),
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
            start_seconds=max(0.0, float(entry.start)),
            original=original,
            translated=translated,
            audio_path=wav_path,
            duration_seconds=duration,
        )

    def _extract_full_audio(self, output_path: Path) -> None:
        run_ffmpeg(
            [
                "-i",
                self._video_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-y",
                str(output_path),
            ]
        )

    def _build_cues(self, source_audio: Path) -> list[ExportCue]:
        if self._temp_dir is None:
            return []

        with measure_stage("export", "asr"):
            segments, info = self._transcribe_with_fallback(source_audio)
            segments = list(segments)
        self._set_progress(34)
        tts_suffix = "wav" if normalize_tts_provider(self._config.tts_provider) == "vieneu" else "mp3"
        items = []

        for index, segment in enumerate(segments):
            if self._stop_requested:
                break
            original = self._transcript_cleaner.clean((segment.text or "").strip(), getattr(info, "language", None))
            if not original:
                continue
            start_seconds = max(0.0, float(segment.start or 0.0))
            end_seconds = max(start_seconds + 0.25, float(segment.end or start_seconds + 0.25))
            duration_seconds = max(0.25, end_seconds - start_seconds)
            items.append((index, original, start_seconds, duration_seconds))
        if not items:
            return []

        with measure_stage("export", "translate_batch", cues=len(items)):
            translated_items = self._translator.translate_many([item[1] for item in items], info.language)

        for (_index, original, _start_seconds, _duration_seconds), translated in zip(
            items, translated_items, strict=False
        ):
            self.segment_ready.emit(original, translated)

        futures = []
        cues: list[ExportCue] = []
        max_workers = _export_worker_count()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for item, translated in zip(items, translated_items, strict=False):
                futures.append(
                    executor.submit(
                        self._build_source_export_cue,
                        source_audio,
                        item[0],
                        item[1],
                        translated,
                        item[2],
                        item[3],
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
                self.progress_changed.emit(
                    f"\u0110ang t\u1ea1o gi\u1ecdng Vi\u1ec7t t\u1ea1i {_format_hhmmss(cue.start_seconds)}..."
                )
        return sorted(cues, key=lambda cue: cue.start_seconds)

    def _build_source_export_cue(
        self,
        source_audio: Path,
        index: int,
        original: str,
        translated: str,
        start_seconds: float,
        duration_seconds: float,
        tts_suffix: str,
    ) -> ExportCue:
        assert self._temp_dir is not None
        tts_path = self._temp_dir / f"cue-{index:05d}.{tts_suffix}"
        reference_path = self._temp_dir / f"cue-{index:05d}-ref.wav"
        matched_path = self._temp_dir / f"cue-{index:05d}-matched.wav"
        with measure_stage("export", "reference", cue=index):
            extract_audio_range(source_audio, start_seconds, duration_seconds, reference_path)
            if self._config.dubbing_auto_voice_gender:
                audio_profile = profile_reference_audio(reference_path)
            else:
                audio_profile = None
        if _tts_disabled(self._config):
            return ExportCue(
                start_seconds=start_seconds,
                original=original,
                translated=translated,
                audio_path=reference_path,
                duration_seconds=duration_seconds,
            )
        voice = self._config.tts_voice
        if audio_profile is not None:
            voice = select_voice_for_gender(
                self._config.tts_provider,
                self._config,
                audio_profile.gender,
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
            )
            final_duration = max(0.25, _probe_duration_seconds(final_audio) or duration_seconds)
        return ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=final_audio,
            duration_seconds=final_duration,
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
                self.progress_changed.emit("Whisper CPU không hỗ trợ float16, chuyển sang int8...")
                return self._switch_whisper_to_cpu(exc)
            if self._whisper_device == "cpu":
                raise
            self.progress_changed.emit("Whisper không chạy được CUDA/Auto, chuyển sang CPU...")
            return self._switch_whisper_to_cpu(exc)

    def _switch_whisper_to_cpu(self, _cause: Exception | None = None) -> WhisperModel:
        self._whisper_device = "cpu"
        self._whisper_compute_type = "int8"
        return WhisperModel(
            self._config.whisper_model,
            device=self._whisper_device,
            compute_type=self._whisper_compute_type,
        )

    def _transcribe_with_fallback(self, source_audio: Path):
        model = self._load_whisper_model()
        try:
            return model.transcribe(
                str(source_audio),
                beam_size=1,
                vad_filter=True,
                language=self._selected_whisper_language(),
            )
        except Exception as exc:
            if self._whisper_device == "cpu" and self._whisper_compute_type != "int8":
                self.progress_changed.emit("Whisper CPU không hỗ trợ compute hiện tại, chuyển sang int8...")
                model = self._switch_whisper_to_cpu(exc)
                return model.transcribe(
                    str(source_audio),
                    beam_size=1,
                    vad_filter=True,
                    language=self._selected_whisper_language(),
                )
            if self._whisper_device == "cpu":
                raise
            self.progress_changed.emit("Whisper lỗi CUDA/CUBLAS, chuyển sang CPU...")
            model = self._switch_whisper_to_cpu(exc)
            return model.transcribe(
                str(source_audio),
                beam_size=1,
                vad_filter=True,
                language=self._selected_whisper_language(),
            )

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return

        parts: list[Path] = []
        cursor = 0.0
        for index, cue in enumerate(sorted(cues, key=lambda item: item.start_seconds)):
            if self._stop_requested:
                return
            self._set_range_progress(76, 88, index, len(cues))

            gap = max(0.0, cue.start_seconds - cursor)
            if gap >= 0.02:
                silence_path = self._temp_dir / f"silence-{index:05d}.wav"
                self._make_silence(gap, silence_path)
                parts.append(silence_path)

            wav_path = self._temp_dir / f"cue-{index:05d}-pcm.wav"
            self._to_wav(cue.audio_path, wav_path)
            parts.append(wav_path)
            duration = self._duration_seconds(wav_path) or cue.duration_seconds or 0.25
            cursor = max(cue.start_seconds, cursor) + duration

        concat_file = self._temp_dir / "concat.txt"
        concat_file.write_text(
            "".join(concat_file_line(path) for path in parts),
            encoding="utf-8",
        )
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-y",
                str(output_path),
            ]
        )

    @staticmethod
    def _make_silence(duration_seconds: float, output_path: Path) -> None:
        ffmpeg_make_silence(duration_seconds, output_path)

    @staticmethod
    def _to_wav(input_path: Path, output_path: Path) -> None:
        ffmpeg_to_wav(input_path, output_path)

    def _trim_leading_silence(self, audio_path: Path) -> Path:
        return ffmpeg_trim_leading_silence(audio_path)

    @staticmethod
    def _duration_seconds(path: Path) -> float:
        return _probe_duration_seconds(path)

    def _mux_video(self, dubbed_audio: Path) -> None:
        quality = _video_quality_settings(self._config.export_video_quality)
        command = [
            "-i",
            self._video_path,
            "-i",
            str(dubbed_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
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
                str(self._output_path),
            ]
        )
        run_ffmpeg(command)


class DocumentReviewExportWorker(QThread):
    progress_changed = Signal(str)
    progress_percent = Signal(int)
    segment_ready = Signal(str, str)
    export_finished = Signal(str)
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
        self._temp_dir: Path | None = None
        self._tts_provider = None
        self._translator = None
        self._transcript_cleaner = TranscriptCleaner(self._config)

    def stop(self) -> None:
        self._stop_requested = True

    def _set_progress(self, value: int) -> None:
        self.progress_percent.emit(max(0, min(100, int(value))))

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
            self.progress_changed.emit("Đang khởi tạo translator và TTS trong nền...")
            self._tts_provider = create_tts_provider(self._config)
            self._translator = VietnameseTranslator(self._config)
            self._set_progress(8)
            if not self._pages:
                raise RuntimeError("Chưa có trang tài liệu để export.")
            if not self._transcript_path.exists():
                raise RuntimeError("Chưa có transcript tài liệu để export.")

            self._temp_dir = Path(tempfile.mkdtemp(prefix="ai-player-document-export-"))
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

            self.progress_changed.emit("Đang đọc transcript tài liệu...")
            self._set_progress(12)
            transcript_cues = _read_srt_cues(self._transcript_path)
            if not transcript_cues:
                raise RuntimeError("Transcript tài liệu không có nội dung để tạo giọng đọc.")

            self.progress_changed.emit("Đang dịch và tạo giọng đọc chất lượng cao...")
            self._set_progress(18)
            audio_cues = self._build_audio_cues(transcript_cues)
            if self._stop_requested:
                return

            dubbed_audio = self._temp_dir / "document-dubbed.wav"
            self.progress_changed.emit("Đang ghép audio lôgng tiếng Việt...")
            self._set_progress(76)
            self._build_aligned_audio(audio_cues, dubbed_audio)
            self._set_progress(84)
            audio_duration = _duration_seconds(dubbed_audio)

            self.progress_changed.emit("Đang dừng video tài liệu để xem lại...")
            self._set_progress(86)
            review_video = self._temp_dir / "document-pages.mp4"
            self._build_document_video(review_video, audio_duration)

            self.progress_changed.emit("Đang xuất MP4 chất lượng cao...")
            self._set_progress(92)
            self._mux_document_video(review_video, dubbed_audio)
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
            if self._stop_requested:
                break
            original = self._transcript_cleaner.clean(cue.text.strip(), self._selected_source_language())
            if not original:
                continue
            items.append((index, cue, original))
        if not items:
            return []

        with measure_stage("document_export", "translate_batch", cues=len(items)):
            translated_items = self._translator.translate_many(
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
                cue = future.result()
                cues.append(cue)
                self._set_range_progress(18, 74, completed, total_cues)
                self.progress_changed.emit(f"Dang tao giong doc tai {_format_hhmmss(cue.start_seconds)}...")
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
        if _tts_disabled(self._config):
            duration = max(0.25, cue.end_seconds - cue.start_seconds)
            _make_silence(duration, wav_path)
            return ExportCue(
                start_seconds=max(0.0, cue.start_seconds),
                original=original,
                translated=translated,
                audio_path=wav_path,
                duration_seconds=duration,
            )
        with self._tts_lock:
            with measure_stage("document_export", "tts", cue=index):
                self._tts_provider.synthesize(translated, tts_path, voice=self._config.tts_voice)
        with measure_stage("document_export", "postprocess", cue=index):
            _to_wav(_trim_leading_silence(tts_path), wav_path)
            duration = _probe_duration_seconds(wav_path)
        return ExportCue(
            start_seconds=max(0.0, cue.start_seconds),
            original=original,
            translated=translated,
            audio_path=wav_path,
            duration_seconds=duration,
        )

    def _build_aligned_audio(self, cues: list[ExportCue], output_path: Path) -> None:
        if self._temp_dir is None:
            return
        parts: list[Path] = []
        cursor = 0.0
        for index, cue in enumerate(sorted(cues, key=lambda item: item.start_seconds)):
            if self._stop_requested:
                return
            self._set_range_progress(76, 84, index, len(cues))
            gap = max(0.0, cue.start_seconds - cursor)
            if gap >= 0.02:
                silence_path = self._temp_dir / f"document-silence-{index:05d}.wav"
                _make_silence(gap, silence_path)
                parts.append(silence_path)
            parts.append(cue.audio_path)
            duration = _duration_seconds(cue.audio_path) or cue.duration_seconds or 0.25
            cursor = max(cue.start_seconds, cursor) + duration

        if not parts:
            _make_silence(1.0, output_path)
            return

        concat_file = self._temp_dir / "document-audio-concat.txt"
        concat_file.write_text(
            "".join(concat_file_line(path) for path in parts),
            encoding="utf-8",
        )
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-y",
                str(output_path),
            ]
        )

    def _build_document_video(self, output_path: Path, audio_duration_seconds: float) -> None:
        if self._temp_dir is None:
            return
        quality = _video_quality_settings(self._config.export_video_quality)
        image_paths = [self._page_image(page, index) for index, page in enumerate(self._pages, start=1)]
        total_page_duration = sum(max(0.5, float(page.duration_seconds)) for page in self._pages)
        extra_duration = max(0.0, audio_duration_seconds - total_page_duration)
        concat_file = self._temp_dir / "document-video-concat.txt"
        lines: list[str] = []
        for index, (page, image_path) in enumerate(zip(self._pages, image_paths, strict=True)):
            duration = max(0.5, float(page.duration_seconds))
            if index == len(self._pages) - 1:
                duration += extra_duration
            lines.append(concat_file_line(image_path))
            lines.append(f"duration {duration:.3f}\n")
        lines.append(concat_file_line(image_paths[-1]))
        concat_file.write_text("".join(lines), encoding="utf-8")
        run_ffmpeg(
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
            ]
        )

    def _page_image(self, page: DocumentPage, index: int) -> Path:
        if page.image_path:
            candidate = Path(page.image_path)
            if candidate.exists():
                return candidate
        if self._temp_dir is None:
            raise RuntimeError("Temp dir chua san sang.")
        return _render_text_page_image(
            page.title or f"Trang {index}",
            page.text,
            self._temp_dir / f"document-page-{index:04d}.png",
        )

    def _mux_document_video(self, video_path: Path, audio_path: Path) -> None:
        quality = _video_quality_settings(self._config.export_video_quality)
        run_ffmpeg(
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
            ]
        )


def _ffmpeg_escape(path: Path) -> str:
    return concat_escape(path)


def _video_quality_settings(value: str) -> VideoQualitySettings:
    quality = str(value or "source").strip().lower()
    if quality == "compact":
        return VideoQualitySettings(crf=28, preset="veryfast", width=1280, height=720, audio_bitrate="160k")
    if quality == "balanced":
        return VideoQualitySettings(crf=23, preset="medium", width=1920, height=1080, audio_bitrate="192k")
    if quality == "high":
        return VideoQualitySettings(crf=18, preset="slow", width=1920, height=1080, audio_bitrate="256k")
    if quality == "archival":
        return VideoQualitySettings(crf=16, preset="slow", width=3840, height=2160, audio_bitrate="320k")
    return VideoQualitySettings(
        crf=18,
        preset="slow",
        width=1920,
        height=1080,
        audio_bitrate="256k",
        copy_source_video=True,
    )


def _scale_filter(width: int, height: int) -> str:
    return (
        f"scale=w=min({int(width)}\\,iw):h=min({int(height)}\\,ih):"
        "force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
    )


def _document_scale_filter(width: int, height: int) -> str:
    width = int(width)
    height = int(height)
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p"
    )


def _read_srt_cues(path: Path) -> list[TranscriptCue]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    cues: list[TranscriptCue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) >= 2 and lines[0].isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        cue_text = " ".join(lines[1:]).strip()
        if not cue_text:
            continue
        cues.append(TranscriptCue(_parse_srt_time(start_raw), _parse_srt_time(end_raw), cue_text))
    return cues


def _parse_srt_time(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)(?:[,.](\d+))?", value.strip())
    if not match:
        return 0.0
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int((millis or "0").ljust(3, "0")[:3]) / 1000.0


def _make_silence(duration_seconds: float, output_path: Path) -> None:
    ffmpeg_make_silence(duration_seconds, output_path)


def _to_wav(input_path: Path, output_path: Path) -> None:
    ffmpeg_to_wav(input_path, output_path)


def _trim_leading_silence(audio_path: Path) -> Path:
    return ffmpeg_trim_leading_silence(audio_path)


def _duration_seconds(path: Path) -> float:
    return probe_duration_seconds(path)


def _probe_duration_seconds(path: Path) -> float:
    return probe_duration_seconds(path)


def _safe_float(value: object) -> float | None:
    return safe_float(value)


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


def _clean_message(value: object) -> str:
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _tts_disabled(config: AppConfig) -> bool:
    return normalize_tts_provider(config.tts_provider) == "none"


def _export_worker_count() -> int:
    configured = os.getenv("AI_PLAYER_EXPORT_WORKERS", "").strip()
    if configured:
        try:
            return max(1, min(8, int(configured)))
        except ValueError:
            pass
    return max(1, min(4, (os.cpu_count() or 2) // 2))


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
