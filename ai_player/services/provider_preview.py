from __future__ import annotations

import math
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from ai_player.core.config import RUNTIME_DIR, AppConfig
from ai_player.core.redaction import compact_redacted_text
from ai_player.services.asr import (
    ASSEMBLYAI_API_BASE,
    SPEECHMATICS_API_BASE,
    effective_asr_provider,
    is_online_asr_provider,
    normalize_asr_provider,
)
from ai_player.services.speaker_voice_selector import (
    HUGGINGFACE_GENDER_API_BASE,
    VoiceGenderSelector,
    _huggingface_gender_url,
    _speaker_gender_online_model_source,
    is_online_speaker_gender_provider,
    normalize_speaker_gender_provider,
)
from ai_player.services.subtitle_ocr import (
    _ocr_frame,
    _tesseract_executable,
    _tesseract_language,
    normalize_ocr_provider,
)
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider
from ai_player.services.tts_base import normalize_tts_provider, tts_output_suffix
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type,
    effective_whisper_device,
    get_shared_whisper_model,
)


class ProviderPreviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderPreviewResult:
    kind: str
    provider: str
    model: str
    elapsed_seconds: float
    message: str
    output_path: str = ""


def preview_provider(kind: str, config: AppConfig) -> ProviderPreviewResult:
    normalized_kind = str(kind or "").strip().lower()
    started = time.perf_counter()
    if normalized_kind == "asr":
        provider, model, message, output_path = _preview_asr(config)
    elif normalized_kind == "ocr":
        provider, model, message, output_path = _preview_ocr(config)
    elif normalized_kind == "translation":
        provider, model, message, output_path = _preview_translation(config)
    elif normalized_kind == "tts":
        provider, model, message, output_path = _preview_tts(config)
    elif normalized_kind == "cleanup":
        provider, model, message, output_path = _preview_cleanup(config)
    elif normalized_kind == "speaker_gender":
        provider, model, message, output_path = _preview_speaker_gender(config)
    else:
        raise ProviderPreviewError(f"Unknown provider preview kind: {kind}")
    return ProviderPreviewResult(
        kind=normalized_kind,
        provider=provider,
        model=model,
        elapsed_seconds=time.perf_counter() - started,
        message=message,
        output_path=output_path,
    )


def _preview_asr(config: AppConfig) -> tuple[str, str, str, str]:
    provider = effective_asr_provider(config)
    if is_online_asr_provider(provider):
        _check_online_asr_endpoint(config, provider)
        return provider, "", "Online ASR endpoint accepted the configured credentials.", ""

    provider = normalize_asr_provider(provider)
    device = effective_whisper_device(config.whisper_device)
    compute = effective_whisper_compute_type(config.whisper_compute_type, device)
    get_shared_whisper_model(
        config.whisper_model,
        device=device,
        compute_type=compute,
        local_files_only=config.whisper_offline,
    )
    return provider, str(config.whisper_model), f"Whisper model loaded on {device}/{compute}.", ""


def _check_online_asr_endpoint(config: AppConfig, provider: str) -> None:
    api_key = str(config.asr_api_key or "").strip()
    if not api_key:
        raise ProviderPreviewError("Online ASR provider requires an API key.")
    timeout = max(5.0, min(30.0, float(config.asr_timeout_seconds or 30.0)))
    if provider == "assemblyai":
        base = str(config.asr_api_base or ASSEMBLYAI_API_BASE).strip().rstrip("/")
        response = requests.get(
            f"{base}/v2/transcript/provider-preview",
            headers={"authorization": api_key},
            timeout=timeout,
        )
        if response.status_code in {200, 404} or _assemblyai_missing_preview_transcript(response):
            return
        _raise_preview_response(response, "AssemblyAI ASR")
    if provider == "speechmatics":
        base = str(config.asr_api_base or SPEECHMATICS_API_BASE).strip().rstrip("/")
        response = requests.get(
            f"{base}/jobs",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": 1},
            timeout=timeout,
        )
        _raise_preview_response(response, "Speechmatics ASR")
        return
    raise ProviderPreviewError(f"Unsupported online ASR provider: {provider}")


def _preview_ocr(config: AppConfig) -> tuple[str, str, str, str]:
    provider = normalize_ocr_provider(config.ocr_provider)
    image_path = _sample_ocr_image_path()
    language = _tesseract_language(config.source_language)
    tesseract = _tesseract_executable() if provider == "tesseract" else None
    result = _ocr_frame(image_path, language, tesseract, config=config)
    if not result.text:
        raise ProviderPreviewError("OCR provider returned no text for the preview image.")
    confidence = "" if result.confidence is None else f" ({result.confidence:.0f}%)"
    return provider, str(config.ocr_model), f"{result.text}{confidence}", str(image_path)


def _preview_translation(config: AppConfig) -> tuple[str, str, str, str]:
    translator = get_shared_vietnamese_translator(config)
    source = "Hello, this is a quick AI Player provider preview."
    translated = translator.translate(source, "en")
    if not str(translated).strip():
        raise ProviderPreviewError("Translator returned an empty preview.")
    return str(config.translator_provider), str(config.local_translation_model), str(translated).strip(), ""


def _preview_tts(config: AppConfig) -> tuple[str, str, str, str]:
    provider_name = normalize_tts_provider(config.tts_provider)
    if provider_name == "none":
        raise ProviderPreviewError("TTS provider is disabled.")
    provider = create_tts_provider(config)
    suffix = tts_output_suffix(provider_name)
    output_path = _preview_dir() / f"tts-preview.{suffix}"
    try:
        provider.synthesize("Xin chao, day la ban nghe thu AI Player.", output_path, voice=config.tts_voice)
    finally:
        provider.close()
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise ProviderPreviewError("TTS provider did not create audio.")
    return (
        provider_name,
        str(config.vieneu_tts_model_name or config.tts_model),
        f"Audio preview: {output_path}",
        str(output_path),
    )


def _preview_cleanup(config: AppConfig) -> tuple[str, str, str, str]:
    cleanup_config = config
    if str(config.transcript_cleanup_mode or "off").strip().lower() == "off":
        from dataclasses import replace

        cleanup_config = replace(config, transcript_cleanup_mode="light")
    cleaner = TranscriptCleaner(cleanup_config)
    cleaned = cleaner.clean("open ai api nay bi nhan dang sai chut.", "vi")
    if not cleaned:
        raise ProviderPreviewError("Cleanup provider returned an empty preview.")
    return str(cleanup_config.transcript_cleanup_provider), str(cleanup_config.transcript_cleanup_model), cleaned, ""


def _preview_speaker_gender(config: AppConfig) -> tuple[str, str, str, str]:
    provider = normalize_speaker_gender_provider(config.speaker_gender_provider)
    sample_path = _sample_audio_path()
    if is_online_speaker_gender_provider(provider):
        model = _speaker_gender_online_model_source(config)
        _check_huggingface_model_endpoint(config, model)
        return provider, model, "Hugging Face model endpoint accepted the configured API key.", ""

    selector = VoiceGenderSelector(config)
    decision = selector.select_voice(sample_path, provider=config.tts_provider, config=config)
    return (
        provider,
        str(config.speaker_gender_model),
        _gender_message(decision.gender, decision.confidence),
        str(sample_path),
    )


def _check_huggingface_model_endpoint(config: AppConfig, model: str) -> None:
    api_key = str(getattr(config, "speaker_gender_api_key", "") or "").strip()
    if not api_key:
        raise ProviderPreviewError("Hugging Face speaker gender provider requires an API key.")
    api_base = str(getattr(config, "speaker_gender_api_base", "") or HUGGINGFACE_GENDER_API_BASE).strip().rstrip("/")
    url = _huggingface_gender_url(api_base, model)
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=max(5.0, min(30.0, float(getattr(config, "speaker_gender_timeout_seconds", 20.0) or 20.0))),
    )
    if response.status_code < 400:
        return
    _raise_preview_response(response, "Hugging Face speaker gender")


def _gender_message(gender: str, confidence: float) -> str:
    clean_gender = str(gender or "unknown").strip() or "unknown"
    return f"{clean_gender} ({max(0.0, min(1.0, float(confidence or 0.0))) * 100:.0f}%)"


def _sample_ocr_image_path() -> Path:
    path = _preview_dir() / "ocr-preview.png"
    image = Image.new("RGB", (520, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((48, 54), "AI Player preview 123", fill="black")
    image.save(path)
    return path


def _sample_audio_path() -> Path:
    path = _preview_dir() / "speaker-preview.wav"
    if path.exists() and path.stat().st_size > 0:
        return path
    sample_rate = 16_000
    duration_seconds = 1.0
    frame_count = int(sample_rate * duration_seconds)
    amplitude = 0.2
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            value = int(32767 * amplitude * math.sin(2 * math.pi * 170 * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        handle.writeframes(bytes(frames))
    return path


def _preview_dir() -> Path:
    path = RUNTIME_DIR / "provider-preview"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _raise_preview_response(response: requests.Response, provider_name: str) -> None:
    if response.status_code < 400:
        return
    if response.status_code in {401, 403}:
        raise ProviderPreviewError(
            f"{provider_name} rejected the API key or endpoint. Check the API key, or set the provider API base "
            "to the correct Speechmatics deployment URL."
        )
    detail = _preview_response_text(response)
    raise ProviderPreviewError(f"{provider_name} request failed with HTTP {response.status_code}: {detail}")


def _assemblyai_missing_preview_transcript(response: requests.Response) -> bool:
    if response.status_code != 400:
        return False
    text = str(getattr(response, "text", "") or "").casefold()
    return "transcript" in text and ("not found" in text or "lookup error" in text)


def _preview_response_text(response: requests.Response) -> str:
    return compact_redacted_text(getattr(response, "text", ""), strip_html=True)
