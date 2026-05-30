from __future__ import annotations

import logging
import sys
import types

from ai_player.services import audio_playback


def test_volume_percent_sanitizes_invalid_values() -> None:
    assert audio_playback._volume_percent(float("nan")) == 100
    assert audio_playback._volume_percent(float("inf")) == 100
    assert audio_playback._volume_percent("bad") == 100
    assert audio_playback._volume_percent(-5) == 0
    assert audio_playback._volume_percent(120.4) == 100


def test_soundcard_playback_fallback_logs_unavailable_speaker(monkeypatch, caplog, tmp_path) -> None:
    fake_soundcard = types.SimpleNamespace(default_speaker=lambda: (_ for _ in ()).throw(RuntimeError("no speaker")))
    monkeypatch.setitem(sys.modules, "soundcard", fake_soundcard)
    monkeypatch.setattr(audio_playback, "_is_pcm_wav", lambda _path: True)

    with caplog.at_level(logging.INFO, logger="ai_player.services.audio_playback"):
        handle = audio_playback._start_soundcard_wav_playback(tmp_path / "demo.wav", volume=100)

    assert handle is None
    assert "falling back to ffplay" in caplog.text
