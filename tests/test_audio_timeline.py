from __future__ import annotations

from ai_player.services.audio_timeline import schedule_timeline_start


def test_schedule_timeline_start_sanitizes_non_finite_values() -> None:
    scheduled_start, scheduled_until = schedule_timeline_start(
        source_start_seconds=float("inf"),
        duration_seconds=float("nan"),
        scheduled_until_seconds="bad",
        policy="strict_start",
    )

    assert scheduled_start == 0.0
    assert scheduled_until == 0.05

