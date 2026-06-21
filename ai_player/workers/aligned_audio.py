from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ai_player.pipeline.export_plan import ExportCue
from ai_player.services.audio_timeline import schedule_timeline_start

ShouldAbort = Callable[[], bool]
SetRangeProgress = Callable[[int, int, int, int], object]
TimelineAudioPath = Callable[[int, ExportCue], Path]
DurationSeconds = Callable[[ExportCue, Path], float]
RunFfmpeg = Callable[[list[object]], object]
TimelineMixArgs = Callable[[list[tuple[Path, float]], Path], list[object]]


def aligned_timeline_inputs(
    cues: list[ExportCue],
    *,
    progress_start: int,
    progress_end: int,
    overlap_policy: str,
    force_avoid_overlap: bool,
    should_abort: ShouldAbort,
    set_range_progress: SetRangeProgress,
    timeline_audio_path: TimelineAudioPath,
    duration_seconds: DurationSeconds,
) -> list[tuple[Path, float]] | None:
    timeline_inputs: list[tuple[Path, float]] = []
    scheduled_until = 0.0
    for index, cue in enumerate(sorted(cues, key=lambda item: item.start_seconds)):
        if should_abort():
            return None
        set_range_progress(progress_start, progress_end, index, len(cues))
        audio_path = timeline_audio_path(index, cue)
        duration = duration_seconds(cue, audio_path) or 0.25
        scheduled_start, scheduled_until = schedule_timeline_start(
            source_start_seconds=cue.start_seconds,
            duration_seconds=duration,
            scheduled_until_seconds=scheduled_until,
            policy=overlap_policy,
            force_avoid_overlap=force_avoid_overlap,
        )
        timeline_inputs.append((audio_path, scheduled_start))
    return timeline_inputs


def mix_timeline_inputs_chunked(
    timeline_inputs: list[tuple[Path, float]],
    output_path: Path,
    *,
    temp_dir: Path,
    run_ffmpeg: RunFfmpeg,
    timeline_mix_args: TimelineMixArgs,
    chunk_size: int = 80,
) -> None:
    if len(timeline_inputs) <= chunk_size:
        run_ffmpeg(timeline_mix_args(timeline_inputs, output_path))
        return

    chunk_inputs: list[tuple[Path, float]] = []
    for chunk_index, chunk in enumerate(_chunks(timeline_inputs, chunk_size)):
        chunk_start = min(start for _path, start in chunk)
        shifted_chunk = [(path, max(0.0, start - chunk_start)) for path, start in chunk]
        chunk_path = temp_dir / f"timeline-mix-{chunk_index:04d}.wav"
        run_ffmpeg(timeline_mix_args(shifted_chunk, chunk_path))
        chunk_inputs.append((chunk_path, chunk_start))

    mix_timeline_inputs_chunked(
        chunk_inputs,
        output_path,
        temp_dir=temp_dir,
        run_ffmpeg=run_ffmpeg,
        timeline_mix_args=timeline_mix_args,
        chunk_size=chunk_size,
    )


def _chunks(items: list[tuple[Path, float]], size: int) -> list[list[tuple[Path, float]]]:
    chunk_size = max(1, int(size))
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]
