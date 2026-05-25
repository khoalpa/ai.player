from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_player.core.config import AppConfig
from ai_player.core.performance import measure_stage
from ai_player.pipeline.export_plan import ExportCue
from ai_player.services.tts import is_non_speech_tts_text
from ai_player.workers.export_utils import (
    _export_reference_audio_required,
    _format_hhmmss,
    _probe_duration_seconds,
    _translate_texts,
    _tts_disabled,
)

MakeSilence = Callable[[float, Path], object]
TrimLeadingSilence = Callable[[Path], Path]
CancelCallback = Callable[[], bool]
MatchToReference = Callable[..., Path]
ExtractAudioRange = Callable[..., object]
ShouldStop = Callable[[], bool]
EmitSegment = Callable[[str, str], object]
BuildSourceExportCue = Callable[[int, str, str, float, float, Path, str, str], ExportCue]
SetRangeProgress = Callable[[int, int, int, int], object]
EmitProgress = Callable[..., object]


@dataclass(frozen=True)
class PreparedSourceExportItem:
    item: object
    reference_path: Path
    voice: str


def source_export_artifact_paths(temp_dir: Path, index: int, tts_suffix: str) -> tuple[Path, Path]:
    return temp_dir / f"cue-{index:05d}.{tts_suffix}", temp_dir / f"cue-{index:05d}-matched.wav"


def translate_export_items(
    *,
    items: list[object],
    translator: Any,
    source_language: str | None,
    emit_segment: EmitSegment,
) -> list[str]:
    with measure_stage("export", "translate_batch", cues=len(items)):
        translated_items = _translate_texts(translator, [item.original for item in items], source_language)
    for item, translated in zip(items, translated_items, strict=False):
        emit_segment(item.original, translated)
    return translated_items


def prepare_source_export_items(
    *,
    items: list[object],
    source_audio: Path,
    temp_dir: Path,
    config: AppConfig,
    voice_selector: Any,
    extract_audio_range: ExtractAudioRange,
    should_stop: ShouldStop,
    cancel_callback: CancelCallback,
) -> list[PreparedSourceExportItem]:
    prepared_items: list[PreparedSourceExportItem] = []
    needs_reference_audio = _export_reference_audio_required(config)
    for item in items:
        if should_stop():
            break
        item_index = int(item.index)
        reference_path = temp_dir / f"cue-{item_index:05d}-ref.wav"
        if needs_reference_audio:
            with measure_stage("export", "reference", cue=item_index):
                extract_audio_range(
                    source_audio,
                    item.start_seconds,
                    item.duration_seconds,
                    reference_path,
                    cancel_callback=cancel_callback,
                )
        else:
            reference_path = source_audio
        voice = config.tts_voice
        if config.dubbing_auto_voice_gender and not _tts_disabled(config):
            voice = voice_selector.select_voice(
                reference_path,
                provider=config.tts_provider,
                config=config,
            ).voice
        prepared_items.append(PreparedSourceExportItem(item, reference_path, voice))
    return prepared_items


def build_prepared_source_export_cues(
    *,
    prepared_items: list[PreparedSourceExportItem],
    translated_items: list[str],
    tts_suffix: str,
    max_workers: int,
    build_source_export_cue: BuildSourceExportCue,
    should_stop: ShouldStop,
    set_range_progress: SetRangeProgress,
    emit_progress: EmitProgress,
) -> list[ExportCue]:
    futures = []
    cues: list[ExportCue] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for prepared, translated in zip(prepared_items, translated_items, strict=False):
            item = prepared.item
            futures.append(
                executor.submit(
                    build_source_export_cue,
                    item.index,
                    item.original,
                    translated,
                    item.start_seconds,
                    item.duration_seconds,
                    prepared.reference_path,
                    prepared.voice,
                    tts_suffix,
                )
            )
        total_segments = max(1, len(futures))
        for completed, future in enumerate(as_completed(futures)):
            if should_stop():
                break
            cue = future.result()
            cues.append(cue)
            set_range_progress(35, 74, completed, total_segments)
            emit_progress("export_progress_creating_voice_at", time=_format_hhmmss(cue.start_seconds))
    return sorted(cues, key=lambda cue: cue.start_seconds)


def build_source_export_cue(
    *,
    index: int,
    original: str,
    translated: str,
    start_seconds: float,
    duration_seconds: float,
    reference_path: Path,
    voice: str,
    tts_suffix: str,
    temp_dir: Path,
    config: AppConfig,
    tts_provider: Any,
    tts_lock: AbstractContextManager[object],
    make_silence: MakeSilence,
    trim_leading_silence: TrimLeadingSilence,
    match_to_reference: MatchToReference,
    cancel_callback: CancelCallback,
) -> ExportCue:
    tts_path, matched_path = source_export_artifact_paths(temp_dir, index, tts_suffix)
    if _tts_disabled(config):
        return ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=reference_path,
            duration_seconds=duration_seconds,
        )
    if is_non_speech_tts_text(translated):
        make_silence(duration_seconds, matched_path)
        return ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=matched_path,
            duration_seconds=duration_seconds,
        )
    with tts_lock:
        with measure_stage("export", "tts", cue=index):
            tts_provider.synthesize(translated, tts_path, voice=voice)
    with measure_stage("export", "postprocess", cue=index):
        final_audio = match_to_reference(
            reference_path=reference_path,
            tts_path=trim_leading_silence(tts_path),
            output_path=matched_path,
            target_duration_seconds=duration_seconds,
            config=config,
            cancel_callback=cancel_callback,
        )
        final_duration = max(0.25, _probe_duration_seconds(final_audio) or duration_seconds)
    return ExportCue(
        start_seconds=start_seconds,
        original=original,
        translated=translated,
        audio_path=final_audio,
        duration_seconds=final_duration,
    )
