from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from ai_player.core.config import AppConfig
from ai_player.core.performance import measure_stage
from ai_player.pipeline.export_plan import ExportCue, TranscriptCue
from ai_player.services.tts import is_non_speech_tts_text
from ai_player.workers.export_utils import _format_hhmmss, _nonempty_file, _tts_disabled
from ai_player.workers.worker_values import voice_tts_suffix

MakeSilence = Callable[[float, Path], object]
TrimLeadingSilence = Callable[[Path], Path]
ToWav = Callable[[Path, Path], object]
CancelCallback = Callable[[], bool]
MatchToReference = Callable[..., Path]
ExtractAudioRange = Callable[..., object]
BuildTargetVoiceCue = Callable[[int, TranscriptCue, Path, str, str], Path]
ProbeDuration = Callable[[Path], float]
ShouldStop = Callable[[], bool]
SetRangeProgress = Callable[[int, int, int, int], object]
EmitProgress = Callable[..., object]


def target_voice_tts_suffix(config: AppConfig) -> str:
    return voice_tts_suffix(config)


def target_voice_artifact_paths(tts_dir: Path, index: int, tts_suffix: str) -> tuple[Path, Path]:
    return tts_dir / f"{index + 1:04d}.{tts_suffix}", tts_dir / f"{index + 1:04d}-aligned.wav"


def build_target_voice_cues(
    *,
    config: AppConfig,
    source_voice: Path,
    source_cues: list[TranscriptCue],
    target_cues: list[TranscriptCue],
    temp_dir: Path,
    voice_selector: Any,
    extract_audio_range: ExtractAudioRange,
    build_target_voice_cue: BuildTargetVoiceCue,
    probe_duration: ProbeDuration,
    should_stop: ShouldStop,
    set_range_progress: SetRangeProgress,
    emit_progress: EmitProgress,
    cancel_callback: CancelCallback,
) -> list[ExportCue]:
    tts_suffix = target_voice_tts_suffix(config)
    cues: list[ExportCue] = []
    total = max(1, len(target_cues))
    for index, (source_cue, target_cue) in enumerate(zip(source_cues, target_cues, strict=False)):
        if should_stop():
            break
        set_range_progress(62, 78, index, total)
        duration = max(0.25, target_cue.end_seconds - target_cue.start_seconds)
        reference_path = temp_dir / f"reference-{index:05d}.wav"
        extract_audio_range(
            source_voice,
            target_cue.start_seconds,
            duration,
            reference_path,
            cancel_callback=cancel_callback,
        )
        voice = config.tts_voice
        if config.dubbing_auto_voice_gender and not _tts_disabled(config):
            voice = voice_selector.select_voice(
                reference_path,
                provider=config.tts_provider,
                config=config,
            ).voice
        audio_path = build_target_voice_cue(index, target_cue, reference_path, voice, tts_suffix)
        cues.append(
            ExportCue(
                start_seconds=target_cue.start_seconds,
                original=source_cue.text,
                translated=target_cue.text,
                audio_path=audio_path,
                duration_seconds=probe_duration(audio_path) or duration,
            )
        )
        emit_progress("export_progress_creating_voice_at", time=_format_hhmmss(target_cue.start_seconds))
    return cues


def build_target_voice_cue(
    *,
    index: int,
    target_cue: TranscriptCue,
    reference_path: Path,
    voice: str,
    tts_suffix: str,
    config: AppConfig,
    tts_dir: Path,
    tts_provider: Any,
    tts_lock: AbstractContextManager[object],
    make_silence: MakeSilence,
    trim_leading_silence: TrimLeadingSilence,
    to_wav: ToWav,
    match_to_reference: MatchToReference,
    cancel_callback: CancelCallback,
) -> Path:
    duration = max(0.25, target_cue.end_seconds - target_cue.start_seconds)
    raw_path, final_path = target_voice_artifact_paths(tts_dir, index, tts_suffix)
    if _tts_disabled(config) or not target_cue.text.strip() or is_non_speech_tts_text(target_cue.text):
        make_silence(duration, final_path)
        return final_path
    with tts_lock:
        with measure_stage("staged_export", "tts", cue=index):
            tts_provider.synthesize(target_cue.text, raw_path, voice=voice)
    with measure_stage("staged_export", "postprocess", cue=index):
        matched_path = match_to_reference(
            reference_path=reference_path,
            tts_path=trim_leading_silence(raw_path),
            output_path=final_path,
            target_duration_seconds=duration,
            config=config,
            cancel_callback=cancel_callback,
        )
    if matched_path != final_path:
        to_wav(matched_path, final_path)
    return final_path if _nonempty_file(final_path) else matched_path
