from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ai_player.services.audio_timeline import schedule_timeline_start
from ai_player.workers.worker_values import finite_seconds

PendingAudio = tuple[float, float, Path, str, str]


@dataclass
class DubbingAudioSchedule:
    pending_audio: list[PendingAudio] = field(default_factory=list)
    scheduled_until: float = 0.0
    subtitle_keys: set[tuple[int, str]] = field(default_factory=set)
    text_keys: list[tuple[str, float]] = field(default_factory=list)

    def reset(self, start_seconds: float = 0.0) -> None:
        self.pending_audio.clear()
        self.subtitle_keys.clear()
        self.text_keys.clear()
        self.scheduled_until = max(0.0, finite_seconds(start_seconds, 0.0))

    def queue_audio(
        self,
        *,
        source_start_seconds: float,
        duration_seconds: float,
        audio_path: Path,
        original: str,
        translated: str,
        policy: object,
        force_avoid_overlap: bool = False,
    ) -> PendingAudio:
        source_start = max(0.0, finite_seconds(source_start_seconds, 0.0))
        duration = max(0.05, finite_seconds(duration_seconds, 0.05))
        scheduled_start, self.scheduled_until = schedule_timeline_start(
            source_start_seconds=source_start,
            duration_seconds=duration,
            scheduled_until_seconds=self.scheduled_until,
            policy=policy,
            force_avoid_overlap=force_avoid_overlap,
        )
        item = (scheduled_start, source_start, audio_path, original, translated)
        self.pending_audio.append(item)
        self.pending_audio.sort(key=lambda audio: audio[0])
        return item

    def register_subtitle(self, start_seconds: float, original_key: str) -> bool:
        key = (int(round(max(0.0, finite_seconds(start_seconds, 0.0)) * 1000)), original_key)
        if key in self.subtitle_keys:
            return False
        self.subtitle_keys.add(key)
        return True

    def prune_text_window(self, start_seconds: float, window_seconds: float) -> None:
        start = max(0.0, finite_seconds(start_seconds, 0.0))
        window = max(0.0, finite_seconds(window_seconds, 0.0))
        self.text_keys = [
            (known_key, known_start)
            for known_key, known_start in self.text_keys
            if start - finite_seconds(known_start, 0.0) <= window
        ]

    def remember_text(self, key: str, start_seconds: float) -> None:
        if key:
            self.text_keys.append((key, max(0.0, finite_seconds(start_seconds, 0.0))))
