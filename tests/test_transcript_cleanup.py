from __future__ import annotations

import logging

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import transcript_cleanup


def test_transcript_cleaner_disabled_normalizes_whitespace() -> None:
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="off"))

    assert cleaner.clean("  Xin   chào   ") == "Xin chào"
    assert cleaner.clean_many(["  A   B  ", ""]) == ["A B", ""]


def test_sanitize_removes_labels_fences_and_explanations() -> None:
    assert transcript_cleanup._sanitize_llm_output("Corrected transcript: Hello world") == "Hello world"
    assert transcript_cleanup._sanitize_llm_output("```text\nTranscript đã sửa: Xin chào\n```") == "Xin chào"
    assert transcript_cleanup._sanitize_llm_output("Giải thích: đã sửa lỗi\nXin chào") == "Xin chào"


def test_safe_cleanup_output_falls_back_for_unsafe_response() -> None:
    original = "Xin chào"
    unsafe = "Giải thích: " + ("đây là phần giải thích rất dài " * 20)

    assert transcript_cleanup._safe_cleanup_output(original, unsafe) == original


def test_clean_many_uses_batch_json_response(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_call(prompt: str, provider: str, config: AppConfig) -> str:
        prompts.append(prompt)
        assert provider == "ollama"
        return '["Xin chào", "Tạm biệt"]'

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", fake_call)
    cleaner = transcript_cleanup.TranscriptCleaner(
        AppConfig(transcript_cleanup_mode="light", transcript_cleanup_provider="ollama")
    )

    assert cleaner.clean_many(["xin chao", "tam biet"], "vi") == ["Xin chào", "Tạm biệt"]
    assert len(prompts) == 1
    assert "JSON array" in prompts[0]


def test_clean_many_falls_back_when_batch_shape_is_wrong(monkeypatch) -> None:
    monkeypatch.setattr(
        transcript_cleanup,
        "_call_cleanup_provider",
        lambda *_args: '["Chỉ một câu"]',
    )
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="light"))

    assert cleaner.clean_many(["câu một", "câu hai"], "vi") == ["câu một", "câu hai"]
    assert cleaner.last_error


def test_cleanup_failure_logs_once_and_returns_original(monkeypatch, caplog) -> None:
    def raise_error(*_args):
        raise transcript_cleanup.TranscriptCleanupError("model unavailable")

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", raise_error)
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="light"))

    with caplog.at_level(logging.WARNING, logger="ai_player.services.transcript_cleanup"):
        assert cleaner.clean("xin chao", "vi") == "xin chao"
        assert cleaner.clean("tam biet", "vi") == "tam biet"

    messages = [record.message for record in caplog.records]
    assert sum("Transcript cleanup failed" in message for message in messages) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("nhẹ", "light"),
        ("mạnh", "strong"),
        ("openai-compatible", "openai"),
        ("headless-local", "local"),
    ],
)
def test_cleanup_aliases(value: str, expected: str) -> None:
    normalizer = (
        transcript_cleanup._cleanup_provider
        if "local" in value or "openai" in value
        else transcript_cleanup._cleanup_mode
    )

    assert normalizer(value) == expected
