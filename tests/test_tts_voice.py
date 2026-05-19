from __future__ import annotations

import pytest

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
