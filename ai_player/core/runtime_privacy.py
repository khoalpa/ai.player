from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_player.core.config import AppConfig
from ai_player.services.asr import effective_asr_provider, is_online_asr_provider
from ai_player.services.speaker_voice_selector import (
    is_online_speaker_gender_provider,
    normalize_speaker_gender_provider,
    normalize_voice_gender_mode,
)
from ai_player.services.subtitle_ocr import is_online_ocr_provider, normalize_ocr_provider
from ai_player.services.transcript_cleanup import is_online_transcript_cleanup_provider
from ai_player.services.translation import is_online_translation_provider, normalize_translator_provider
from ai_player.services.tts_base import is_online_tts_provider, normalize_tts_provider


@dataclass(frozen=True)
class RuntimePrivacyItem:
    feature: str
    data_type: str
    provider: str
    detail: str
    detail_key: str


def build_runtime_privacy(config: AppConfig) -> tuple[RuntimePrivacyItem, ...]:
    items: list[RuntimePrivacyItem] = []

    asr_provider = effective_asr_provider(config)
    if is_online_asr_provider(asr_provider):
        items.append(
            RuntimePrivacyItem(
                "ASR",
                "audio",
                asr_provider,
                "Speech audio may be sent to the selected speech recognition provider.",
                "runtime_privacy_detail_asr",
            )
        )

    translation_provider = normalize_translator_provider(config.translator_provider)
    if is_online_translation_provider(translation_provider):
        items.append(
            RuntimePrivacyItem(
                "Translation",
                "text",
                translation_provider,
                "Transcript text may be sent to the selected translation provider.",
                "runtime_privacy_detail_translation",
            )
        )

    tts_provider = normalize_tts_provider(config.tts_provider)
    if tts_provider == "edge" or is_online_tts_provider(tts_provider):
        items.append(
            RuntimePrivacyItem(
                "TTS",
                "text",
                tts_provider,
                "Text to synthesize may be sent to the selected voice provider.",
                "runtime_privacy_detail_tts",
            )
        )

    ocr_provider = normalize_ocr_provider(config.ocr_provider)
    if is_online_ocr_provider(ocr_provider):
        items.append(
            RuntimePrivacyItem(
                "OCR",
                "image",
                ocr_provider,
                "Subtitle frames or document images may be sent to the selected OCR provider.",
                "runtime_privacy_detail_ocr",
            )
        )

    if _cleanup_enabled(config) and is_online_transcript_cleanup_provider(config.transcript_cleanup_provider):
        items.append(
            RuntimePrivacyItem(
                "Transcript cleanup",
                "text",
                _provider_name(config.transcript_cleanup_provider),
                "Transcript text may be sent to the selected cleanup provider.",
                "runtime_privacy_detail_cleanup",
            )
        )

    speaker_gender_provider = normalize_speaker_gender_provider(config.speaker_gender_provider)
    if _speaker_gender_ai_enabled(config) and is_online_speaker_gender_provider(speaker_gender_provider):
        items.append(
            RuntimePrivacyItem(
                "Speaker gender",
                "audio",
                speaker_gender_provider,
                "Short voice samples may be sent to the selected speaker analysis provider.",
                "runtime_privacy_detail_speaker_gender",
            )
        )

    return tuple(items)


def format_runtime_privacy(
    items: tuple[RuntimePrivacyItem, ...],
    *,
    offline_text: str,
    translate: Callable[[str], str] | None = None,
) -> str:
    if not items:
        return offline_text
    return "\n".join(
        f"{item.feature}: {item.provider} ({item.data_type}) - {_privacy_detail(item, translate)}" for item in items
    )


def _privacy_detail(item: RuntimePrivacyItem, translate: Callable[[str], str] | None) -> str:
    if translate is None:
        return item.detail
    translated = translate(item.detail_key)
    return translated if translated != item.detail_key else item.detail


def _cleanup_enabled(config: AppConfig) -> bool:
    return str(config.transcript_cleanup_mode or "off").strip().lower() != "off"


def _speaker_gender_ai_enabled(config: AppConfig) -> bool:
    return (
        bool(config.dubbing_auto_voice_gender)
        and normalize_voice_gender_mode(config.dubbing_auto_voice_gender_mode) == "ai"
    )


def _provider_name(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_") or "unknown"
