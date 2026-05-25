from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ai_player.pipeline.export_plan import ExportCue
from ai_player.services.audio_timeline import schedule_timeline_start

ShouldAbort = Callable[[], bool]
SetRangeProgress = Callable[[int, int, int, int], object]
TimelineAudioPath = Callable[[int, ExportCue], Path]
DurationSeconds = Callable[[ExportCue, Path], float]


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
