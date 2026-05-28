from __future__ import annotations

from ai_player.workers.dubbing_schedule import DubbingAudioSchedule


def test_dubbing_audio_schedule_queues_sorted_audio(tmp_path) -> None:
    schedule = DubbingAudioSchedule(scheduled_until=10.0)
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"

    schedule.queue_audio(
        source_start_seconds=2.0,
        duration_seconds=1.0,
        audio_path=second,
        original="two",
        translated="hai",
        policy="strict_start",
    )
    schedule.queue_audio(
        source_start_seconds=1.0,
        duration_seconds=1.0,
        audio_path=first,
        original="one",
        translated="mot",
        policy="strict_start",
    )

    assert schedule.pending_audio == [
        (1.0, 1.0, first, "one", "mot"),
        (2.0, 2.0, second, "two", "hai"),
    ]
    assert schedule.scheduled_until == 10.0


def test_dubbing_audio_schedule_tracks_subtitle_and_text_windows() -> None:
    schedule = DubbingAudioSchedule()

    assert schedule.register_subtitle(1.234, "hello")
    assert not schedule.register_subtitle(1.234, "hello")

    schedule.remember_text("old", 0.0)
    schedule.remember_text("new", 40.0)
    schedule.prune_text_window(40.0, 30.0)

    assert schedule.text_keys == [("new", 40.0)]
