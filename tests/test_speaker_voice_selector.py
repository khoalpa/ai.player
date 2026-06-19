from __future__ import annotations

import logging
import math
import struct
import wave
from pathlib import Path

from ai_player.core.config import INTERNAL_VIENEU_STANDARD_GGUF, AppConfig
from ai_player.services import audio_matcher
from ai_player.services import speaker_voice_selector as selector
from ai_player.services.audio_matcher import AudioProfile


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text="") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text

    def json(self):
        return self._payload


def _profile(gender: str, confidence: float) -> AudioProfile:
    pitch = 130.0 if gender == "male" else 220.0
    return AudioProfile(
        gender=gender,
        median_pitch_hz=pitch,
        mean_volume_db=-20.0,
        duration_seconds=1.5,
        pitch_iqr_hz=20.0,
        voiced_ratio=0.7,
        gender_confidence=confidence,
    )


def test_normalize_voice_gender_mode_aliases() -> None:
    assert selector.normalize_voice_gender_mode("safe") == "stable"
    assert selector.normalize_voice_gender_mode("model") == "ai"
    assert selector.normalize_voice_gender_mode("weird") == "balanced"


def test_normalize_speaker_gender_provider_aliases() -> None:
    assert selector.normalize_speaker_gender_provider("hf") == "huggingface_gender"
    assert selector.normalize_speaker_gender_provider("offline") == "local"
    assert selector.normalize_speaker_gender_provider("weird") == "local"


def test_balanced_selector_uses_gendered_voice(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(selector, "_profile_for_mode", lambda _path, _mode, **_kwargs: _profile("male", 0.74))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="balanced",
        tts_provider="vieneu",
        tts_voice="Doan",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    decision = selector.VoiceGenderSelector(config).select_voice(tmp_path / "ref.wav", provider="vieneu", config=config)

    assert decision.gender == "male"
    assert decision.voice == "Binh"


def test_stable_selector_waits_for_repeated_gender(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(selector, "_profile_for_mode", lambda _path, _mode, **_kwargs: _profile("female", 0.8))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="stable",
        tts_provider="vieneu",
        tts_voice="Binh",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )
    voice_selector = selector.VoiceGenderSelector(config)

    first = voice_selector.select_voice(tmp_path / "ref1.wav", provider="vieneu", config=config)
    second = voice_selector.select_voice(tmp_path / "ref2.wav", provider="vieneu", config=config)

    assert first.gender == "unknown"
    assert first.voice == "Binh"
    assert second.gender == "female"
    assert second.voice == "Doan"


def test_ai_mode_falls_back_to_pitch_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(selector, "_ai_profile_reference_audio", lambda _path, **_kwargs: None)
    monkeypatch.setattr(selector, "profile_reference_audio", lambda _path: _profile("female", 0.9))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="ai",
        tts_provider="vieneu",
        tts_voice="Binh",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    decision = selector.VoiceGenderSelector(config).select_voice(Path("ref.wav"), provider="vieneu", config=config)

    assert decision.gender == "female"
    assert decision.voice == "Doan"


def test_huggingface_gender_provider_uses_online_classification(monkeypatch, tmp_path) -> None:
    calls = []
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"audio")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(payload=[{"label": "female", "score": 0.91}, {"label": "male", "score": 0.08}])

    monkeypatch.setattr(selector.requests, "post", fake_post)
    monkeypatch.setattr(selector, "profile_reference_audio", lambda _path: _profile("male", 0.65))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="ai",
        speaker_gender_provider="huggingface_gender",
        speaker_gender_api_key="hf-token",
        speaker_gender_model="audeering/wav2vec2-large-robust-6-ft-age-gender",
        tts_provider="vieneu",
        tts_voice="Binh",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    decision = selector.VoiceGenderSelector(config).select_voice(reference, provider="vieneu", config=config)

    assert decision.gender == "female"
    assert decision.confidence == 0.91
    assert decision.voice == "Doan"
    assert decision.profile is not None
    assert decision.profile.detector == "huggingface"
    assert calls[0][0].endswith("/audeering%2Fwav2vec2-large-robust-6-ft-age-gender")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer hf-token"


def test_huggingface_gender_provider_falls_back_when_missing_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(selector.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(selector, "_speaker_gender_ai_model_source", lambda _config=None: "")
    monkeypatch.setattr(selector, "profile_reference_audio", lambda _path: _profile("male", 0.9))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="ai",
        speaker_gender_provider="huggingface_gender",
        speaker_gender_api_key="",
        tts_provider="vieneu",
        tts_voice="Doan",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    decision = selector.VoiceGenderSelector(config).select_voice(tmp_path / "ref.wav", provider="vieneu", config=config)

    assert decision.gender == "male"
    assert decision.voice == "Binh"


def test_ai_model_source_uses_local_default_when_available(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "speaker-gender"
    model_path.mkdir()
    monkeypatch.delenv("AI_PLAYER_SPEAKER_GENDER_AI_MODEL", raising=False)
    monkeypatch.setattr(selector, "LOCAL_SPEAKER_GENDER_MODEL_PATH", model_path)

    assert selector._speaker_gender_ai_model_source() == str(model_path)


def test_ai_model_source_prefers_explicit_environment(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "speaker-gender"
    monkeypatch.setenv("AI_PLAYER_SPEAKER_GENDER_AI_MODEL", str(model_path))

    assert selector._speaker_gender_ai_model_source() == str(model_path)


def test_ai_model_source_uses_config_before_environment(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / "env-speaker-gender"
    config_path = tmp_path / "configured-speaker-gender"
    monkeypatch.setenv("AI_PLAYER_SPEAKER_GENDER_AI_MODEL", str(env_path))

    assert selector._speaker_gender_ai_model_source(AppConfig(speaker_gender_model=str(config_path))) == str(
        config_path
    )


def test_real_audio_selector_uses_pitch_gender_when_ffprobe_has_no_duration(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(audio_matcher, "probe_duration_seconds", lambda _path: 0.0)
    male_reference = tmp_path / "male.wav"
    female_reference = tmp_path / "female.wav"
    _write_sine_wav(male_reference, 130.0)
    _write_sine_wav(female_reference, 220.0)
    config = AppConfig(
        dubbing_auto_voice_gender_mode="balanced",
        tts_provider="vieneu",
        tts_voice="Doan",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    male = selector.VoiceGenderSelector(config).select_voice(male_reference, provider="vieneu", config=config)
    female = selector.VoiceGenderSelector(config).select_voice(female_reference, provider="vieneu", config=config)

    assert male.gender == "male"
    assert male.voice == "Binh"
    assert male.confidence >= 0.62
    assert male.profile is not None
    assert male.profile.duration_seconds >= 1.4
    assert female.gender == "female"
    assert female.voice == "Doan"
    assert female.confidence >= 0.62
    assert female.profile is not None
    assert female.profile.duration_seconds >= 1.4


def test_real_audio_selector_keeps_default_voice_for_ambiguous_pitch(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(audio_matcher, "probe_duration_seconds", lambda _path: 0.0)
    reference = tmp_path / "ambiguous.wav"
    _write_sine_wav(reference, 175.0)
    config = AppConfig(
        dubbing_auto_voice_gender_mode="sensitive",
        tts_provider="vieneu",
        tts_voice="Binh",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    decision = selector.VoiceGenderSelector(config).select_voice(reference, provider="vieneu", config=config)

    assert decision.gender == "unknown"
    assert decision.voice == "Binh"
    assert decision.reason == "pitch:unknown"


def test_selector_logs_voice_decision(monkeypatch, tmp_path, caplog) -> None:
    monkeypatch.setattr(selector, "_profile_for_mode", lambda _path, _mode, **_kwargs: _profile("male", 0.74))
    config = AppConfig(
        dubbing_auto_voice_gender_mode="balanced",
        tts_provider="vieneu",
        tts_voice="Doan",
        tts_male_voice="Binh",
        tts_female_voice="Doan",
        vieneu_tts_mode="standard",
        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
    )

    with caplog.at_level(logging.INFO, logger=selector.__name__):
        selector.VoiceGenderSelector(config).select_voice(tmp_path / "ref.wav", provider="vieneu", config=config)

    assert "Auto voice decision" in caplog.text
    assert "gender=male" in caplog.text
    assert "voice=Binh" in caplog.text
    assert "reason=pitch:accepted" in caplog.text


def _write_sine_wav(path: Path, frequency_hz: float, duration_seconds: float = 1.5) -> None:
    sample_rate = 16_000
    frames = bytearray()
    for index in range(int(duration_seconds * sample_rate)):
        sample = 0.35 * math.sin(2.0 * math.pi * frequency_hz * index / sample_rate)
        frames.extend(struct.pack("<h", int(sample * 32767)))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
