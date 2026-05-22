from __future__ import annotations

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
