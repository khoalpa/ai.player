from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services.asr import is_online_asr_provider, normalize_asr_provider
from ai_player.services.ffmpeg import ffmpeg_executable, ffplay_executable
from ai_player.services.subtitle_ocr import is_online_ocr_provider, normalize_ocr_provider
from ai_player.services.translation import is_online_translation_provider
from ai_player.services.tts import is_online_tts_provider, normalize_tts_provider


@dataclass(frozen=True)
class RuntimeHealthItem:
    name: str
    status: str
    detail: str


def build_runtime_health(config: AppConfig) -> tuple[RuntimeHealthItem, ...]:
    return (
        _asr_health(config),
        _translation_health(config),
        _tts_health(config),
        _ocr_health(config),
        _export_health(),
    )


def format_runtime_health(items: tuple[RuntimeHealthItem, ...]) -> str:
    return "\n".join(f"{item.name}: {item.status} - {item.detail}" for item in items)


def _asr_health(config: AppConfig) -> RuntimeHealthItem:
    provider = normalize_asr_provider(config.asr_provider)
    if is_online_asr_provider(provider):
        if _has_text(config.asr_api_key):
            return RuntimeHealthItem("ASR", "READY", f"{provider} API key is configured.")
        return RuntimeHealthItem("ASR", "ATTENTION", f"{provider} requires an API key.")
    if _path_exists(config.whisper_model):
        return RuntimeHealthItem("ASR", "READY", f"Whisper model: {config.whisper_model}")
    return RuntimeHealthItem("ASR", "ATTENTION", f"Whisper model path is missing: {config.whisper_model}")


def _translation_health(config: AppConfig) -> RuntimeHealthItem:
    provider = str(config.translator_provider or "").strip().lower()
    if provider == "none":
        return RuntimeHealthItem("Translation", "OFF", "Translation is disabled.")
    if is_online_translation_provider(provider):
        if _has_text(config.translator_api_key):
            return RuntimeHealthItem("Translation", "READY", f"{provider} API key is configured.")
        return RuntimeHealthItem("Translation", "ATTENTION", f"{provider} requires an API key.")
    if _path_exists(config.local_translation_model):
        return RuntimeHealthItem("Translation", "READY", f"Local model: {config.local_translation_model}")
    return RuntimeHealthItem(
        "Translation",
        "ATTENTION",
        f"Local translation model path is missing: {config.local_translation_model}",
    )


def _tts_health(config: AppConfig) -> RuntimeHealthItem:
    provider = normalize_tts_provider(config.tts_provider)
    if provider == "none":
        return RuntimeHealthItem("TTS", "OFF", "TTS provider is disabled.")
    if provider == "edge":
        return RuntimeHealthItem("TTS", "READY", "Edge TTS is selected; Internet may be required.")
    if provider == "amazon_polly":
        if _has_text(config.tts_api_key) and _has_text(config.tts_api_secret):
            return RuntimeHealthItem("TTS", "READY", "Amazon Polly credentials are configured.")
        return RuntimeHealthItem("TTS", "ATTENTION", "Amazon Polly requires an access key and secret.")
    if is_online_tts_provider(provider):
        if _has_text(config.tts_api_key):
            return RuntimeHealthItem("TTS", "READY", f"{provider} API key is configured.")
        return RuntimeHealthItem("TTS", "ATTENTION", f"{provider} requires an API key.")
    if provider == "vieneu":
        model = config.vieneu_tts_model_name or config.vieneu_tts_path
        if _path_exists(model):
            return RuntimeHealthItem("TTS", "READY", f"VieNeu model: {model}")
        return RuntimeHealthItem("TTS", "ATTENTION", f"VieNeu model path is missing: {model}")
    return RuntimeHealthItem("TTS", "READY", f"{provider} is selected.")


def _ocr_health(config: AppConfig) -> RuntimeHealthItem:
    provider = normalize_ocr_provider(config.ocr_provider)
    if is_online_ocr_provider(provider):
        if provider == "ocr_space" and not _has_text(config.ocr_api_key):
            return RuntimeHealthItem("OCR", "READY", "OCR.space demo key will be used; rate limits may apply.")
        if _has_text(config.ocr_api_key):
            return RuntimeHealthItem("OCR", "READY", f"{provider} API key is configured.")
        return RuntimeHealthItem("OCR", "ATTENTION", f"{provider} requires an API key.")
    if _tool_exists("tesseract"):
        return RuntimeHealthItem("OCR", "READY", "Tesseract is available.")
    return RuntimeHealthItem("OCR", "ATTENTION", "Tesseract executable is missing.")


def _export_health() -> RuntimeHealthItem:
    tools = (
        ("FFmpeg", ffmpeg_executable()),
        ("ffplay", ffplay_executable()),
    )
    missing = [name for name, executable in tools if not _executable_exists(executable)]
    if missing:
        return RuntimeHealthItem("Export", "ATTENTION", f"Missing required media tool(s): {', '.join(missing)}.")
    return RuntimeHealthItem("Export", "READY", "FFmpeg and ffplay are available.")


def _has_text(value: object) -> bool:
    return bool(str(value or "").strip())


def _path_exists(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and Path(text).exists()


def _tool_exists(name: str) -> bool:
    return _executable_exists(shutil.which(name) or name)


def _executable_exists(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    path = Path(text)
    return path.is_file() or shutil.which(text) is not None
