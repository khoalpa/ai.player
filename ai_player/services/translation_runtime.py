from __future__ import annotations

import threading
from dataclasses import dataclass

from ai_player.core.config import AppConfig
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.services.translation import PassthroughTranslator, VietnameseTranslator, effective_translator_provider
from ai_player.services.workflow_cache import get_text_result, put_text_result


@dataclass(frozen=True)
class TranslationRuntimeKey:
    provider: str
    model: str
    device: str
    offline: bool
    max_tokens: int
    beams: int
    target_language: str
    api_base: str
    api_key: str
    api_region: str
    timeout_seconds: int
    preserve_terms: bool
    preserved_terms: str


class SharedVietnameseTranslator:
    def __init__(self, config: AppConfig) -> None:
        self._translator = VietnameseTranslator(config)
        self._runtime_key = translation_runtime_key(config)
        self._lock = threading.Lock()

    def translate(self, text: str, source_language: str | None = None) -> str:
        with self._lock:
            runtime_key = getattr(self, "_runtime_key", None)
            if runtime_key is None:
                return self._translator.translate(text, source_language)
            cached = get_text_result(
                "translation",
                runtime_key,
                text,
                source_language=source_language,
            )
            if cached is not None:
                return cached
            translated = self._translator.translate(text, source_language)
            return put_text_result(
                "translation",
                runtime_key,
                text,
                translated,
                source_language=source_language,
            )

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        with self._lock:
            runtime_key = getattr(self, "_runtime_key", None)
            if runtime_key is None:
                return self._translator.translate_many(texts, source_language)
            results: list[str | None] = []
            missing_texts: list[str] = []
            missing_indexes: list[int] = []
            seen_missing: dict[str, int] = {}
            for index, text in enumerate(texts):
                cached = get_text_result(
                    "translation",
                    runtime_key,
                    text,
                    source_language=source_language,
                )
                if cached is not None:
                    results.append(cached)
                    continue
                normalized = " ".join(str(text or "").split())
                duplicate_index = seen_missing.get(normalized)
                if duplicate_index is not None:
                    results.append(None)
                    missing_indexes.append(index)
                    continue
                seen_missing[normalized] = len(missing_texts)
                missing_texts.append(text)
                missing_indexes.append(index)
                results.append(None)

            if missing_texts:
                translated_missing = _align_text_results(
                    missing_texts,
                    self._translator.translate_many(missing_texts, source_language),
                )
                translated_by_normalized = {
                    " ".join(str(text or "").split()): translated
                    for text, translated in zip(missing_texts, translated_missing, strict=False)
                }
                for index in missing_indexes:
                    text = texts[index]
                    translated = translated_by_normalized.get(" ".join(str(text or "").split()), str(text or ""))
                    results[index] = put_text_result(
                        "translation",
                        runtime_key,
                        text,
                        translated,
                        source_language=source_language,
                    )
            return [str(result or "") for result in results]


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
        api_base=str(getattr(config, "translator_api_base", "")),
        api_key=str(getattr(config, "translator_api_key", "")),
        api_region=str(getattr(config, "translator_api_region", "")),
        timeout_seconds=_int_value(getattr(config, "translator_timeout_seconds", 30), default=30, minimum=1),
        preserve_terms=bool(config.preserve_source_terms),
        preserved_terms="\n".join(
            part for part in (str(config.preserved_source_terms), str(config.preserved_english_terms)) if part.strip()
        ),
    )


def _int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)


def _align_text_results(fallback_texts: list[str], results: object) -> list[str]:
    if isinstance(results, str | bytes):
        result_items = []
    else:
        try:
            result_items = list(results)
        except TypeError:
            result_items = []
    aligned = []
    for index, fallback in enumerate(fallback_texts):
        result = result_items[index] if index < len(result_items) else fallback
        if isinstance(result, bytes):
            result = result.decode("utf-8", errors="replace")
        elif not isinstance(result, str):
            result = fallback
        aligned.append(" ".join(str(result or fallback or "").split()) or fallback)
    return aligned
