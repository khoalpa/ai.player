from __future__ import annotations

from ai_player.domain.translation_quality import (
    translate_with_quality_guard,
    translation_needs_retry,
)


def test_translation_quality_rejects_empty_extreme_and_missing_numbers() -> None:
    assert translation_needs_retry("Price is 25 dollars", "")
    assert translation_needs_retry("Price is 25 dollars", "Giá tiền")
    assert translation_needs_retry("hello", "x" * 30)
    assert not translation_needs_retry("Price is 25 dollars", "Giá là 25 đô la")


def test_translation_quality_retries_then_uses_valid_result() -> None:
    results = iter(["Giá tiền", "Giá là 25 đô la"])
    assert (
        translate_with_quality_guard(lambda _text, _language: next(results), "Price is 25 dollars", "en")
        == "Giá là 25 đô la"
    )


def test_translation_quality_falls_back_to_source_after_errors_at_call_site() -> None:
    assert translate_with_quality_guard(lambda _text, _language: "", "hello world", "en") == "hello world"


def test_translation_quality_retries_transient_provider_error() -> None:
    calls = 0

    def translate(_text: str, _language: str | None) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return "xin chào thế giới"

    assert translate_with_quality_guard(translate, "hello world", "en") == "xin chào thế giới"
    assert calls == 2


def test_translation_quality_reports_retry_and_source_fallback() -> None:
    events: list[str] = []
    result = translate_with_quality_guard(
        lambda _text, _language: "",
        "hello world",
        "en",
        on_retry=lambda: events.append("retry"),
        on_fallback=lambda: events.append("fallback"),
    )

    assert result == "hello world"
    assert events == ["retry", "fallback"]
