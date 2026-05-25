from __future__ import annotations

import threading
from dataclasses import dataclass

from ai_player.core.config import AppConfig
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.services.translation import PassthroughTranslator, VietnameseTranslator, effective_translator_provider


@dataclass(frozen=True)
class TranslationRuntimeKey:
    provider: str
    model: str
    device: str
    offline: bool
    max_tokens: int
    beams: int
    target_language: str
    preserve_terms: bool
    preserved_terms: str


class SharedVietnameseTranslator:
    def __init__(self, config: AppConfig) -> None:
        self._translator = VietnameseTranslator(config)
        self._lock = threading.Lock()

    def translate(self, text: str, source_language: str | None = None) -> str:
        with self._lock:
            return self._translator.translate(text, source_language)

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        with self._lock:
            return self._translator.translate_many(texts, source_language)


_TRANSLATOR_CACHE_LOCK = threading.Lock()
_TRANSLATOR_CACHE: dict[TranslationRuntimeKey, SharedVietnameseTranslator] = {}


def get_shared_vietnamese_translator(config: AppConfig):
    if effective_translator_provider(config) == "none":
        return PassthroughTranslator()
    key = translation_runtime_key(config)
    with _TRANSLATOR_CACHE_LOCK:
        cached = _TRANSLATOR_CACHE.get(key)
        if cached is None:
            cached = SharedVietnameseTranslator(config)
            _TRANSLATOR_CACHE[key] = cached
        return cached


def clear_shared_vietnamese_translators() -> None:
    with _TRANSLATOR_CACHE_LOCK:
        _TRANSLATOR_CACHE.clear()


def translation_runtime_key(config: AppConfig) -> TranslationRuntimeKey:
    return TranslationRuntimeKey(
        provider=effective_translator_provider(config),
        model=str(config.local_translation_model),
        device=str(config.local_translation_device),
        offline=bool(config.local_translation_offline),
        max_tokens=_int_value(config.translation_max_tokens, default=152, minimum=1),
        beams=_int_value(config.translation_num_beams, default=2, minimum=1),
        target_language=str(config.target_language),
        preserve_terms=bool(config.preserve_source_terms),
        preserved_terms="\n".join(
            part for part in (str(config.preserved_source_terms), str(config.preserved_english_terms)) if part.strip()
        ),
    )


def _int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)
