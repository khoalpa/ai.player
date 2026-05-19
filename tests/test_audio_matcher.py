from __future__ import annotations

from pathlib import Path

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import audio_matcher
from ai_player.services.audio_matcher import match_tts_to_reference


def test_audio_match_plan_clamps_auto_tempo_and_gain(monkeypatch, tmp_path) -> None:
    reference_path = tmp_path / "reference.wav"
    tts_path = tmp_path / "tts.wav"
    monkeypatch.setattr(audio_matcher, "audio_duration_seconds", lambda _path: 2.0)

    def fake_mean_volume(path: Path, *, sample_rate: int | None = None, channels: int | None = None) -> float:
        if path == reference_path:
            assert sample_rate is None
            assert channels is None
            return -18.0
        assert sample_rate == 44100
        assert channels == 2
        return -30.0

    monkeypatch.setattr(audio_matcher, "mean_volume_db", fake_mean_volume)
    config = AppConfig(
        dubbing_auto_match_audio=True,
        dubbing_speed_percent=10,
        dubbing_speed_min=0.75,
        dubbing_speed_max=1.35,
        dubbing_volume_gain_min_db=-10.0,
        dubbing_volume_gain_max_db=8.0,
    )

    plan = audio_matcher._build_audio_match_plan(
        reference_path=reference_path,
        tts_path=tts_path,
        target_duration_seconds=1.0,
        config=config,
    )

    assert plan.tempo == pytest.approx(1.485)
    assert plan.gain_db == 8.0
    assert plan.filters == (
        "atempo=1.4850",
        "aformat=sample_rates=44100:channel_layouts=stereo",
        "volume=8.00dB",
    )


def test_audio_match_plan_skips_tiny_gain(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(audio_matcher, "audio_duration_seconds", lambda _path: 1.0)

    volumes = {
        tmp_path / "reference.wav": -20.0,
        tmp_path / "tts.wav": -20.3,
    }
    monkeypatch.setattr(audio_matcher, "mean_volume_db", lambda path, **_kwargs: volumes[path])
    config = AppConfig(
        dubbing_auto_match_audio=True,
        dubbing_speed_percent=0,
        dubbing_speed_min=0.75,
        dubbing_speed_max=1.35,
    )

    plan = audio_matcher._build_audio_match_plan(
        reference_path=tmp_path / "reference.wav",
        tts_path=tmp_path / "tts.wav",
        target_duration_seconds=1.0,
        config=config,
    )

    assert plan.gain_db == pytest.approx(0.3)
    assert plan.filters == ()


def test_match_tts_to_reference_returns_original_when_no_filters(monkeypatch, tmp_path) -> None:
    tts_path = tmp_path / "tts.wav"
    output_path = tmp_path / "matched.wav"
    config = AppConfig(dubbing_auto_match_audio=False, dubbing_speed_percent=0)

    def fail_run_ffmpeg(_args: list[object]) -> None:
        raise AssertionError("ffmpeg should not run without audio match filters")

    monkeypatch.setattr(audio_matcher, "run_ffmpeg", fail_run_ffmpeg)

    result = match_tts_to_reference(
        reference_path=tmp_path / "reference.wav",
        tts_path=tts_path,
        output_path=output_path,
        target_duration_seconds=1.0,
        config=config,
    )

    assert result == tts_path
    assert not output_path.exists()


def test_match_tts_to_reference_formats_audio_before_volume(monkeypatch, tmp_path) -> None:
    reference_path = tmp_path / "reference.wav"
    tts_path = tmp_path / "tts.wav"
    output_path = tmp_path / "matched.wav"
    monkeypatch.setattr(audio_matcher, "audio_duration_seconds", lambda _path: 2.0)
    monkeypatch.setattr(
        audio_matcher,
        "mean_volume_db",
        lambda path, **_kwargs: -20.0 if path == reference_path else -30.0,
    )
    captured: dict[str, list[object]] = {}

    def fake_run_ffmpeg(args: list[object]) -> None:
        captured["args"] = args
        output_path.write_bytes(b"matched")

    monkeypatch.setattr(audio_matcher, "run_ffmpeg", fake_run_ffmpeg)
    config = AppConfig(
        dubbing_auto_match_audio=True,
        dubbing_speed_percent=0,
        dubbing_speed_min=0.5,
        dubbing_speed_max=2.0,
        dubbing_volume_gain_max_db=8.0,
    )

    result = match_tts_to_reference(
        reference_path=reference_path,
        tts_path=tts_path,
        output_path=output_path,
        target_duration_seconds=1.0,
        config=config,
    )

    assert result == output_path
    filters = captured["args"][captured["args"].index("-af") + 1]
    assert filters == "atempo=2.0000,aformat=sample_rates=44100:channel_layouts=stereo,volume=8.00dB"
    assert captured["args"][captured["args"].index("-ar") + 1] == "44100"
    assert captured["args"][captured["args"].index("-ac") + 1] == "2"
