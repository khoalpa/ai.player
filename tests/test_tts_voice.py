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
