from __future__ import annotations

from ai_player.services import audio_playback


def test_volume_percent_sanitizes_invalid_values() -> None:
    assert audio_playback._volume_percent(float("nan")) == 100
    assert audio_playback._volume_percent(float("inf")) == 100
    assert audio_playback._volume_percent("bad") == 100
    assert audio_playback._volume_percent(-5) == 0
    assert audio_playback._volume_percent(120.4) == 100

