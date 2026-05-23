from __future__ import annotations

import queue

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import tts


@pytest.mark.parametrize(("value", "expected"), [("edge-tts", "edge"), ("off", "none"), ("local", "vieneu")])
def test_normalize_tts_provider(value: str, expected: str) -> None:
    assert tts.normalize_tts_provider(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("standard", "standard"), ("api", "remote"), ("cuda", "fast")])
def test_normalize_vieneu_mode(value: str, expected: str) -> None:
    assert tts.normalize_vieneu_mode(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("gpu", "cuda"), ("cpu", "cpu"), ("weird", "auto")])
def test_normalize_vieneu_device(value: str, expected: str) -> None:
    assert tts.normalize_vieneu_device(value) == expected


@pytest.mark.parametrize(
    ("provider", "voice", "expected"),
    [
        ("edge", "vi-VN-NamMinhNeural", "male"),
        ("edge", "vi-VN-HoaiMyNeural", "female"),
        ("vieneu", "Binh", "male"),
        ("vieneu", "Doan", "female"),
        ("vieneu", "unknown", "unknown"),
    ],
)
def test_voice_gender(provider: str, voice: str, expected: str) -> None:
    assert tts.voice_gender(provider, voice) == expected


def test_vieneu_preferred_voice_fallbacks_use_southern_voices_first() -> None:
    turbo_config = AppConfig(vieneu_tts_mode="turbo")
    standard_config = AppConfig(vieneu_tts_mode="standard")

    assert tts._preferred_voice_ids("vieneu", turbo_config, "female")[0] == "Thục Đoan"
    assert tts._preferred_voice_ids("vieneu", turbo_config, "male")[0] == "Xuân Vĩnh"
    assert tts._preferred_voice_ids("vieneu", standard_config, "female")[0] == "Doan"
    assert tts._preferred_voice_ids("vieneu", standard_config, "male")[0] == "Vinh"


def test_tts_cache_text_normalizes_unicode_and_format_chars() -> None:
    assert tts._cache_text("Cafe\u0301\u200b") == "Caf\u00e9"


@pytest.mark.parametrize("value", ["Ah...", "ừm", "hmmm", "mm mm", "..."])
def test_non_speech_tts_text_detects_filler_sounds(value: str) -> None:
    assert tts.is_non_speech_tts_text(value)


@pytest.mark.parametrize("value", ["xin chào", "có", "AI Player"])
def test_non_speech_tts_text_keeps_spoken_words(value: str) -> None:
    assert not tts.is_non_speech_tts_text(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("\u4f55\u3067\u3059\u304b", ""),
        ("\u0110\u00e2y l\u00e0 \u5148\u8f29", "\u0110\u00e2y l\u00e0"),
        ("AI Player", "AI Player"),
        ("\u00ea \u00ea \u00ea", ""),
    ],
)
def test_prepare_tts_text_removes_source_script_residue(value: str, expected: str) -> None:
    assert tts.prepare_tts_text(value, "vi") == expected


def test_pathological_tts_duration_detects_short_text_that_runs_too_long() -> None:
    assert tts.is_pathological_tts_duration("l\u00e0 g\u00ec", 5.0, target_duration_seconds=1.0)
    assert not tts.is_pathological_tts_duration("l\u00e0 g\u00ec", 1.2, target_duration_seconds=1.0)


def test_pathological_tts_duration_ignores_invalid_durations() -> None:
    assert not tts.is_pathological_tts_duration("hello", "bad", target_duration_seconds=float("inf"))
    assert not tts.is_pathological_tts_duration("hello", float("nan"), target_duration_seconds="bad")


def test_vieneu_infer_kwargs_sanitize_invalid_numeric_values() -> None:
    kwargs = tts._build_vieneu_infer_kwargs(
        engine=object(),
        text="hello",
        voice="voice",
        temperature=float("nan"),
        max_chars="bad",
    )

    assert kwargs["temperature"] == 0.6
    assert kwargs["max_chars"] == 160


def test_tts_cache_path_sanitizes_invalid_vieneu_numeric_config(tmp_path) -> None:
    config = AppConfig(vieneu_tts_temperature=float("inf"), vieneu_tts_max_chars_chunk="bad")

    cache_path = tts._tts_cache_path("vieneu", config, "hello", "voice", tmp_path / "out.wav")

    assert cache_path.suffix == ".wav"


def test_vieneu_server_read_response_rejects_invalid_json_payload() -> None:
    class FakeProcess:
        def poll(self):
            return None

    client = tts.VieNeuServerClient.__new__(tts.VieNeuServerClient)
    client._process = FakeProcess()
    client._output_queue = queue.Queue()
    client._output_queue.put("AI_PLAYER_JSON:not-json\n")

    with pytest.raises(tts.TTSError, match="invalid JSON"):
        client._read_response(timeout_seconds=1)


def test_vieneu_server_read_response_requires_json_object() -> None:
    class FakeProcess:
        def poll(self):
            return None

    client = tts.VieNeuServerClient.__new__(tts.VieNeuServerClient)
    client._process = FakeProcess()
    client._output_queue = queue.Queue()
    client._output_queue.put("AI_PLAYER_JSON:[]\n")

    with pytest.raises(tts.TTSError, match="invalid JSON payload"):
        client._read_response(timeout_seconds=1)


def test_cached_tts_provider_reuses_cached_audio(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    cache_path = tmp_path / "cache.wav"

    class FakeProvider(tts.BaseTTSProvider):
        def synthesize(self, text, output_path, voice=None) -> None:
            calls.append(str(text))
            output_path.write_bytes(b"audio")

    monkeypatch.setattr(tts, "_tts_cache_path", lambda *_args, **_kwargs: cache_path)
    provider = tts.CachedTTSProvider(FakeProvider(), AppConfig(), "vieneu")

    provider.synthesize("hello", tmp_path / "first.wav", voice="Doan")
    provider.synthesize("hello", tmp_path / "second.wav", voice="Doan")

    assert calls == ["hello"]
    assert (tmp_path / "second.wav").read_bytes() == b"audio"
