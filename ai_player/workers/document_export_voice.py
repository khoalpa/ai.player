from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from ai_player.core.config import AppConfig
from ai_player.core.performance import measure_stage
from ai_player.pipeline.export_plan import ExportCue, TranscriptCue
from ai_player.services.tts import is_non_speech_tts_text
from ai_player.workers.export_utils import (
    _cue_time_bounds,
    _format_hhmmss,
    _probe_duration_seconds,
    _tts_disabled,
)

MakeSilence = Callable[[float, Path], object]
TrimLeadingSilence = Callable[[Path], Path]
ToWav = Callable[[Path, Path], object]
BuildDocumentExportCue = Callable[[int, TranscriptCue, str, str, str], ExportCue]
SetRangeProgress = Callable[[int, int, int, int], object]
EmitProgress = Callable[..., object]


def document_export_artifact_paths(temp_dir: Path, index: int, tts_suffix: str) -> tuple[Path, Path]:
    return temp_dir / f"document-cue-{index:05d}.{tts_suffix}", temp_dir / f"document-cue-{index:05d}.wav"


def build_document_export_cue(
    *,
    index: int,
    cue: TranscriptCue,
    original: str,
    translated: str,
    tts_suffix: str,
    temp_dir: Path,
    config: AppConfig,
    tts_provider: Any,
    tts_lock: AbstractContextManager[object],
    make_silence: MakeSilence,
    trim_leading_silence: TrimLeadingSilence,
    to_wav: ToWav,
) -> ExportCue:
    tts_path, wav_path = document_export_artifact_paths(temp_dir, index, tts_suffix)
    cue_start, cue_end = _cue_time_bounds(cue)
    duration = max(0.25, cue_end - cue_start)
    if _tts_disabled(config) or is_non_speech_tts_text(translated):
        make_silence(duration, wav_path)
        return ExportCue(
            start_seconds=cue_start,
            original=original,
            translated=translated,
            audio_path=wav_path,
            duration_seconds=duration,
        )
    with tts_lock:
        with measure_stage("document_export", "tts", cue=index):
            tts_provider.synthesize(translated, tts_path, voice=config.tts_voice)
    with measure_stage("document_export", "postprocess", cue=index):
        to_wav(trim_leading_silence(tts_path), wav_path)
        duration = _probe_duration_seconds(wav_path)
    return ExportCue(
        start_seconds=cue_start,
        original=original,
        translated=translated,
        audio_path=wav_path,
        duration_seconds=duration,
    )


def build_prepared_document_export_cues(
    *,
    items: list[tuple[int, TranscriptCue, str]],
    translated_items: list[str],
    tts_suffix: str,
    max_workers: int,
    build_document_export_cue: BuildDocumentExportCue,
    should_stop: Callable[[], bool],
    set_range_progress: SetRangeProgress,
    emit_progress: EmitProgress,
) -> list[ExportCue]:
    cues: list[ExportCue] = []
    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for item, translated in zip(items, translated_items, strict=False):
            futures.append(
                executor.submit(
                    build_document_export_cue,
                    item[0],
                    item[1],
                    item[2],
                    translated,
                    tts_suffix,
                )
            )
        total_cues = max(1, len(futures))
        for completed, future in enumerate(as_completed(futures)):
            if should_stop():
                break
            cue = future.result()
            cues.append(cue)
            set_range_progress(18, 74, completed, total_cues)
            emit_progress("document_export_progress_creating_voice_at", time=_format_hhmmss(cue.start_seconds))
    return sorted(cues, key=lambda cue: cue.start_seconds)
