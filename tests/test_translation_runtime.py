from __future__ import annotations

from dataclasses import replace

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import translation_runtime


def test_translation_runtime_key_normalizes_provider() -> None:
    key = translation_runtime.translation_runtime_key(AppConfig(translator_provider="ct2"))

    assert key.provider == "nllb_ct2"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("local_translation_model", "other"),
        ("local_translation_device", "cpu"),
        ("translation_max_tokens", 99),
        ("preserved_english_terms", "API"),
    ],
)
def test_translation_runtime_key_changes_for_cache_relevant_fields(field: str, value) -> None:
    base = AppConfig()
    changed = replace(base, **{field: value})

    assert translation_runtime.translation_runtime_key(base) != translation_runtime.translation_runtime_key(changed)


def test_none_provider_returns_passthrough() -> None:
    translator = translation_runtime.get_shared_vietnamese_translator(AppConfig(translator_provider="none"))

    assert translator.translate("  Hello   world ", "en") == "Hello world"


def test_shared_translator_is_cached(monkeypatch) -> None:
    class FakeVietnameseTranslator:
        def __init__(self, _config) -> None:
            self.calls = 0

        def translate(self, text, source_language=None):
            self.calls += 1
            return text

        def translate_many(self, texts, source_language=None):
            return list(texts)

    translation_runtime.clear_shared_vietnamese_translators()
    monkeypatch.setattr(translation_runtime, "VietnameseTranslator", FakeVietnameseTranslator)
    config = AppConfig(translator_provider="nllb")

    first = translation_runtime.get_shared_vietnamese_translator(config)
    second = translation_runtime.get_shared_vietnamese_translator(config)

    assert first is second


def test_clear_shared_translators_discards_cache(monkeypatch) -> None:
    class FakeVietnameseTranslator:
        def __init__(self, _config) -> None:
            pass

        def translate(self, text, source_language=None):
            return text

        def translate_many(self, texts, source_language=None):
            return list(texts)

    monkeypatch.setattr(translation_runtime, "VietnameseTranslator", FakeVietnameseTranslator)
    config = AppConfig(translator_provider="nllb")
    first = translation_runtime.get_shared_vietnamese_translator(config)
    translation_runtime.clear_shared_vietnamese_translators()

    assert translation_runtime.get_shared_vietnamese_translator(config) is not first


def test_shared_translator_delegates_translate_many(monkeypatch) -> None:
    class FakeTranslator:
        def translate(self, text, source_language=None):
            return text.upper()

        def translate_many(self, texts, source_language=None):
            return [text.upper() for text in texts]

    shared = translation_runtime.SharedVietnameseTranslator.__new__(translation_runtime.SharedVietnameseTranslator)
    shared._translator = FakeTranslator()
    shared._lock = translation_runtime.threading.Lock()

    assert shared.translate_many(["a", "b"], "en") == ["A", "B"]
