from __future__ import annotations

import asyncio
import atexit
import base64
import datetime as _datetime
import hashlib
import hmac
import html
import importlib.util
import inspect
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import edge_tts
import requests

from ai_player.core.config import (
    INTERNAL_VIENEU_STANDARD_CODEC,
    INTERNAL_VIENEU_STANDARD_GGUF,
    INTERNAL_VIENEU_STANDARD_PATH,
    INTERNAL_VIENEU_TTS_PATH,
    INTERNAL_VIENEU_TURBO_DECODER,
    INTERNAL_VIENEU_TURBO_ENCODER,
    INTERNAL_VIENEU_TURBO_GGUF,
    INTERNAL_VIENEU_TURBO_PATH,
    PROJECT_ROOT,
    RUNTIME_DIR,
    AppConfig,
)
from ai_player.core.offline_env import pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.value_utils import clean_message as _core_clean_message
from ai_player.core.value_utils import clean_text as _core_clean_text
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.services.tts_voices import (
    AMAZON_POLLY_VOICES,
    AZURE_TTS_VOICES,
    EDGE_VOICES,
    ELEVENLABS_TTS_VOICES,
    GOOGLE_TTS_VOICES,
    STANDARD_VIENEU_VOICES,
    TURBO_VIENEU_VOICES,
    VieNeuModelOption,
    VoiceOption,
    available_tts_provider_options,
    available_vieneu_mode_options,
    migrate_vieneu_legacy_voice_id,
)
from ai_player.services.tts_voices import (
    normalize_voice_token as _normalize_voice_token,
)
from ai_player.services.tts_voices import (
    read_vieneu_voices as _read_vieneu_voices,
)
from ai_player.services.tts_voices import (
    vieneu_model_voices_path as _vieneu_model_voices_path,
)
from ai_player.services.tts_voices import voice_gender as _catalog_voice_gender


class TTSError(RuntimeError):
    pass


_VIENEU_ENGINE_LOCK = threading.Lock()
_VIENEU_ENGINE_CACHE: dict[tuple[str, ...], Any] = {}
_VIENEU_SERVER_CACHE_LOCK = threading.Lock()
_VIENEU_SERVER_CACHE: dict[tuple[str, ...], VieNeuServerClient] = {}
_TTS_CACHE_LOCK = threading.Lock()
_TTS_CACHE_KEY_LOCKS: dict[Path, threading.Lock] = {}
_EDGE_TTS_LOCK = threading.Lock()
_VIENEU_REMOTE_CODEC_REPO = "neuphonic/neucodec-onnx-decoder-int8"
AZURE_TTS_DEFAULT_REGION = "eastus"
GOOGLE_TTS_API_BASE = "https://texttospeech.googleapis.com/v1/text:synthesize"
ELEVENLABS_TTS_API_BASE = "https://api.elevenlabs.io/v1"
ONLINE_TTS_PROVIDERS = {"azure_tts", "google_tts", "amazon_polly", "elevenlabs_tts"}


def available_tts_providers() -> list[VoiceOption]:
    return available_tts_provider_options()


def available_vieneu_modes() -> list[VoiceOption]:
    return available_vieneu_mode_options()


def available_vieneu_models(mode: str, config: AppConfig) -> list[VieNeuModelOption]:
    selected_mode = normalize_vieneu_mode(mode)
    if selected_mode == "remote":
        return [
            VieNeuModelOption(
                "pnnbao-ump/VieNeu-TTS",
                "VieNeu-TTS remote API",
                False,
            )
        ]
    if selected_mode == "standard":
        models = _local_vieneu_standard_models()
        models.extend(
            [
                VieNeuModelOption(
                    "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf",
                    "VieNeu-TTS 0.3B q4 GGUF (HF/cache)",
                    False,
                ),
                VieNeuModelOption(
                    "pnnbao-ump/VieNeu-TTS",
                    "VieNeu-TTS standard (HF/cache)",
                    False,
                ),
            ]
        )
        return _unique_vieneu_models(models)

    default_local = INTERNAL_VIENEU_TURBO_PATH / "vieneu-tts-v2-turbo.gguf"
    models = _local_vieneu_turbo_models()
    if default_local.exists():
        models.insert(
            0, VieNeuModelOption(str(default_local.resolve()), "VieNeu-TTS v2 Turbo GGUF (local offline)", True)
        )
    models.extend(
        [
            VieNeuModelOption(
                "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
                "VieNeu-TTS v2 Turbo GGUF (HF/cache)",
                False,
            ),
        ]
    )
    return _unique_vieneu_models(models)


def available_voices(provider: str, config: AppConfig | None = None) -> list[VoiceOption]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "none":
        return [VoiceOption("none", "Không TTS")]
    if normalized_provider == "vieneu":
        return _vieneu_voices(config)
    if normalized_provider == "azure_tts":
        return AZURE_TTS_VOICES
    if normalized_provider == "google_tts":
        return GOOGLE_TTS_VOICES
    if normalized_provider == "amazon_polly":
        return AMAZON_POLLY_VOICES
    if normalized_provider == "elevenlabs_tts":
        return ELEVENLABS_TTS_VOICES
    return EDGE_VOICES


def select_voice_for_gender(provider: str, config: AppConfig, gender: str) -> str:
    requested_gender = str(gender or "unknown").strip().lower()
    if requested_gender not in {"male", "female"}:
        return config.tts_voice

    voices = available_voices(provider, config)
    available_ids = {voice.id for voice in voices}
    configured_voice = config.tts_male_voice if requested_gender == "male" else config.tts_female_voice
    if configured_voice in available_ids:
        return configured_voice
    migrated_voice = migrate_vieneu_legacy_voice_id(
        configured_voice,
        tuple((voice.name, voice.id) for voice in voices),
    )
    if migrated_voice in available_ids:
        return migrated_voice

    current_gender = voice_gender(provider, config.tts_voice)
    if current_gender == requested_gender:
        return config.tts_voice

    preferred = _preferred_voice_ids(provider, config, requested_gender)
    for voice_id in preferred:
        if voice_id in available_ids:
            return voice_id

    for voice in voices:
        if voice_gender(provider, voice.id) == requested_gender:
            return voice.id
    return config.tts_voice


def voice_gender(provider: str, voice_id: object) -> str:
    return _catalog_voice_gender(provider, voice_id)


def _compatible_edge_voice_id(voice_id: object) -> str:
    raw = str(voice_id or "").strip()
    available_ids = {voice.id for voice in EDGE_VOICES}
    if raw in available_ids:
        return raw
    gender = voice_gender("edge", raw)
    if gender == "male":
        return "vi-VN-NamMinhNeural"
    return "vi-VN-HoaiMyNeural"


def _compatible_online_voice_id(provider: str, voice_id: object) -> str:
    raw = str(voice_id or "").strip()
    normalized_provider = normalize_tts_provider(provider)
    voices = available_voices(provider)
    available_ids = {voice.id for voice in voices}
    if raw in available_ids:
        return raw
    if raw and normalized_provider in {"amazon_polly", "elevenlabs_tts"}:
        return raw
    if raw.startswith(("vi-VN-", "en-US-", "en-GB-")) and normalized_provider in {"azure_tts", "google_tts"}:
        return raw
    gender = voice_gender(provider, raw)
    if gender == "male":
        return _preferred_online_voice_id(provider, "male")
    return _preferred_online_voice_id(provider, "female")


def _preferred_online_voice_id(provider: str, gender: str) -> str:
    normalized_provider = normalize_tts_provider(provider)
    preferred = {
        "azure_tts": {"female": "vi-VN-HoaiMyNeural", "male": "vi-VN-NamMinhNeural"},
        "google_tts": {"female": "vi-VN-Neural2-A", "male": "vi-VN-Neural2-D"},
        "amazon_polly": {"female": "Joanna", "male": "Matthew"},
        "elevenlabs_tts": {"female": "21m00Tcm4TlvDq8ikWAM", "male": "JBFqnCBsd6RMkjVDRZzb"},
    }
    return preferred.get(normalized_provider, preferred["azure_tts"]).get(gender, preferred["azure_tts"]["female"])


def create_tts_provider(config: AppConfig) -> BaseTTSProvider:
    provider = normalize_tts_provider(config.tts_provider)
    if provider == "none":
        return NoTTSProvider(config)
    if provider == "vieneu":
        return CachedTTSProvider(VieNeuTTSProvider(config), config, provider)
    if provider in ONLINE_TTS_PROVIDERS:
        return CachedTTSProvider(OnlineTTSProvider(config, provider), config, provider)
    return CachedTTSProvider(EdgeTTSProvider(config), config, provider)


def normalize_tts_provider(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if raw in {"vieneu", "vieneutts", "vieneucore", "local", "offline"}:
        return "vieneu"
    if raw in {"edge", "edgetts", "edgecli"}:
        return "edge"
    if raw in {"azure", "azuretts", "microsofttts", "microsoftazuretts"}:
        return "azure_tts"
    if raw in {"google", "googletts", "googlecloudtts", "gcp", "gcptts"}:
        return "google_tts"
    if raw in {"amazon", "amazonpolly", "polly", "awspolly"}:
        return "amazon_polly"
    if raw in {"elevenlabs", "elevenlabstts", "eleven", "elevenlabsapi"}:
        return "elevenlabs_tts"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"


def tts_output_suffix(provider: object) -> str:
    return "wav" if normalize_tts_provider(provider) == "vieneu" else "mp3"


def is_online_tts_provider(provider: object) -> bool:
    return normalize_tts_provider(provider) in ONLINE_TTS_PROVIDERS


_NON_SPEECH_TTS_TOKENS = {
    "a",
    "aa",
    "aaa",
    "ah",
    "aha",
    "aw",
    "e",
    "eh",
    "er",
    "err",
    "ha",
    "hah",
    "haha",
    "hahaha",
    "haiz",
    "hm",
    "hmm",
    "hmmm",
    "huh",
    "m",
    "mh",
    "mhm",
    "mm",
    "mmh",
    "mmm",
    "mmmm",
    "o",
    "oh",
    "oo",
    "ooh",
    "u",
    "uh",
    "uhh",
    "uhm",
    "um",
    "umm",
}


def is_non_speech_tts_text(value: object) -> bool:
    text = _clean_text(value)
    if not text:
        return True

    normalized = unicodedata.normalize("NFD", text.lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("đ", "d")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        return True
    if len(tokens) > 4 or any(any(ch.isdigit() for ch in token) for token in tokens):
        return False
    return all(token in _NON_SPEECH_TTS_TOKENS or _looks_like_drawn_out_vocalization(token) for token in tokens)


def prepare_tts_text(value: object, target_language: object = "vi") -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if _target_uses_latin_script(target_language):
        text = _strip_non_latin_source_script(text)
    return "" if is_non_speech_tts_text(text) else text


def is_pathological_tts_duration(
    text: object,
    duration_seconds: float,
    target_duration_seconds: float | None = None,
) -> bool:
    duration = _finite_duration(duration_seconds)
    if duration <= 0:
        return False
    clean_text = prepare_tts_text(text)
    if not clean_text:
        return True

    normalized = unicodedata.normalize("NFD", clean_text.lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    letter_count = sum(1 for ch in normalized if ch.isalpha())
    token_count = len(tokens)
    target_duration = _finite_duration(target_duration_seconds)

    if letter_count <= 12:
        short_ceiling = max(3.0, target_duration * 2.5)
        return duration > short_ceiling

    estimated_natural_duration = max(1.0, token_count * 0.45 + letter_count * 0.065)
    ceiling = max(8.0, estimated_natural_duration * 2.8, target_duration * 2.8)
    return duration > ceiling


def _finite_duration(value: object) -> float:
    try:
        duration = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(duration):
        return 0.0
    return max(0.0, duration)


def _looks_like_drawn_out_vocalization(token: str) -> bool:
    if len(token) < 2 or len(token) > 10:
        return False
    if len(set(token)) == 1 and token[0] in {"a", "e", "h", "m", "o", "u"}:
        return True
    return bool(re.fullmatch(r"h*m+h*", token) or re.fullmatch(r"[auo]+h*", token))


def _target_uses_latin_script(target_language: object) -> bool:
    normalized = str(target_language or "vi").strip().lower().split("-", 1)[0]
    return normalized in {"vi", "en", "de", "es", "fr", "id", "it", "pt", "tr"}


def _strip_non_latin_source_script(value: str) -> str:
    text = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]+", " ", value)
    text = re.sub(r"[\u0400-\u04ff\u0590-\u05ff\u0600-\u06ff\u0e00-\u0e7f]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return " ".join(text.split()).strip(" ,.;:!?")


def normalize_vieneu_mode(value: object) -> str:
    raw = str(value or "turbo").strip().lower().replace("-", "_")
    aliases = {
        "local": "turbo",
        "default": "turbo",
        "turbo": "turbo",
        "standard": "standard",
        "remote": "turbo",
        "api": "turbo",
        "remote_api": "turbo",
        "fast": "fast",
        "gpu": "fast",
        "cuda": "fast",
        "turbo_gpu": "turbo_gpu",
        "xpu": "xpu",
    }
    if raw in aliases:
        return aliases[raw]
    raise TTSError(f"VieNeu mode không hợp lệ: {value!r}")


def normalize_vieneu_device(value: object) -> str:
    raw = str(value or "auto").strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "default": "auto",
        "prefer_gpu": "auto",
        "gpu": "cuda",
        "cuda": "cuda",
        "cuda:0": "cuda",
        "cpu": "cpu",
    }
    if raw in aliases:
        return aliases[raw]
    return "auto"


def resolve_vieneu_runtime_device(value: object) -> str:
    device = normalize_vieneu_device(value)
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def normalize_vieneu_backend(value: object) -> str:
    raw = str(value or "auto").strip().lower().replace("-", "_")
    if raw in {"auto", "native", "lmdeploy"}:
        return raw
    return "auto"


def resolve_vieneu_effective_mode(core: object, mode: object, device: object) -> str:
    selected_mode = normalize_vieneu_mode(mode)
    return "standard" if selected_mode == "standard" else "turbo"


def resolve_vieneu_runtime_backend(mode: object, model_name: object, device: object, backend: object) -> str:
    requested = normalize_vieneu_backend(backend)
    resolved_mode = normalize_vieneu_mode(mode)
    resolved_device = resolve_vieneu_runtime_device(device)
    clean_model = str(model_name or "").strip().lower()
    supports_lmdeploy = resolved_mode == "standard" and resolved_device == "cuda"
    if "gguf" in clean_model or "turbo" in clean_model:
        supports_lmdeploy = False
    if requested == "native":
        return "native"
    if requested == "lmdeploy":
        return "lmdeploy" if supports_lmdeploy and importlib.util.find_spec("lmdeploy") else "native"
    if not supports_lmdeploy:
        return "native"
    return "lmdeploy" if importlib.util.find_spec("lmdeploy") else "native"


class BaseTTSProvider:
    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class NoTTSProvider(BaseTTSProvider):
    def __init__(self, _config: AppConfig) -> None:
        pass

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        raise TTSError("Không TTS không tạo audio mới.")


class CachedTTSProvider(BaseTTSProvider):
    def __init__(self, inner: BaseTTSProvider, config: AppConfig, provider: str) -> None:
        self._inner = inner
        self._config = config
        self._provider = normalize_tts_provider(provider)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not _tts_cache_enabled():
            self._inner.synthesize(text, output_path, voice=voice)
            return

        cache_path = _tts_cache_path(self._provider, self._config, text, voice or self._config.tts_voice, output_path)
        cache_lock = _tts_cache_lock_for(cache_path)
        with cache_lock:
            if cache_path.exists() and cache_path.stat().st_size > 0:
                shutil.copyfile(cache_path, output_path)
                return

            self._inner.synthesize(text, output_path, voice=voice)
            if not output_path.exists() or output_path.stat().st_size <= 0:
                return

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_cache_path = cache_path.with_name(f"{cache_path.name}.tmp")
            if cache_path.exists() and cache_path.stat().st_size > 0:
                return
            shutil.copyfile(output_path, temp_cache_path)
            temp_cache_path.replace(cache_path)

    def close(self) -> None:
        self._inner.close()


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._voice = _compatible_edge_voice_id(config.tts_voice)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError("Edge TTS cannot read empty text.")
        output_path = Path(output_path)
        voice_id = _compatible_edge_voice_id(voice or self._voice)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with _EDGE_TTS_LOCK:
                    asyncio.run(self._synthesize(clean_text, output_path, voice_id))
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
                raise TTSError("Edge TTS returned an empty audio file.")
            except Exception as exc:
                last_error = exc
                _remove_tts_output(output_path)
                if attempt >= 2:
                    break
                time.sleep(0.4 * (attempt + 1))
        detail = _clean_message(last_error) if last_error is not None else "unknown error"
        raise TTSError(f"Edge TTS failed for voice '{voice_id}': {detail}") from last_error

    async def _synthesize(self, text: str, output_path: Path, voice: str) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))


class OnlineTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig, provider: str) -> None:
        self._config = config
        self._provider = normalize_tts_provider(provider)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError(f"{self._provider} cannot read empty text.")
        output_path = Path(output_path)
        voice_id = _compatible_online_voice_id(self._provider, voice or self._config.tts_voice)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                audio = self._request_audio(clean_text, voice_id)
                _write_tts_audio(output_path, audio)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
                raise TTSError(f"{self._provider} returned an empty audio file.")
            except Exception as exc:
                last_error = exc
                _remove_tts_output(output_path)
                if attempt >= 2:
                    break
                time.sleep(0.4 * (attempt + 1))
        detail = _clean_message(last_error) if last_error is not None else "unknown error"
        raise TTSError(f"{self._provider} failed for voice '{voice_id}': {detail}") from last_error

    def _request_audio(self, text: str, voice_id: str) -> bytes:
        if self._provider == "azure_tts":
            return self._request_azure(text, voice_id)
        if self._provider == "google_tts":
            return self._request_google(text, voice_id)
        if self._provider == "amazon_polly":
            return self._request_amazon_polly(text, voice_id)
        if self._provider == "elevenlabs_tts":
            return self._request_elevenlabs(text, voice_id)
        raise TTSError(f"Unsupported online TTS provider: {self._provider}")

    def _request_azure(self, text: str, voice_id: str) -> bytes:
        api_key = _required_tts_api_key(self._config, "Azure TTS")
        region = str(getattr(self._config, "tts_api_region", "") or AZURE_TTS_DEFAULT_REGION).strip()
        api_base = _tts_api_base(self._config)
        url = api_base or f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        locale = _voice_language_code(voice_id, default="vi-VN")
        escaped_text = html.escape(text, quote=False)
        escaped_voice = html.escape(voice_id, quote=True)
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}' "
            f"xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice xml:lang='{locale}' name='{escaped_voice}'>{escaped_text}</voice>"
            "</speak>"
        )
        response = requests.post(
            url,
            data=ssml.encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "ai-player",
            },
            timeout=_tts_timeout(self._config),
        )
        _raise_for_tts_response(response, "Azure TTS")
        return response.content

    def _request_google(self, text: str, voice_id: str) -> bytes:
        api_key = _required_tts_api_key(self._config, "Google Cloud TTS")
        url = _google_tts_url(_tts_api_base(self._config) or GOOGLE_TTS_API_BASE, api_key)
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": _voice_language_code(voice_id, default="vi-VN"),
                "name": voice_id,
            },
            "audioConfig": {"audioEncoding": "MP3"},
        }
        response = requests.post(url, json=payload, timeout=_tts_timeout(self._config))
        _raise_for_tts_response(response, "Google Cloud TTS")
        data = _response_json(response, "Google Cloud TTS")
        audio_content = str(data.get("audioContent") or "")
        if not audio_content:
            raise TTSError("Google Cloud TTS response did not include audioContent.")
        try:
            return base64.b64decode(audio_content)
        except Exception as exc:
            raise TTSError("Google Cloud TTS returned invalid base64 audioContent.") from exc

    def _request_amazon_polly(self, text: str, voice_id: str) -> bytes:
        access_key = _required_tts_api_key(self._config, "Amazon Polly")
        secret_key = _required_tts_api_secret(self._config, "Amazon Polly")
        region = str(getattr(self._config, "tts_api_region", "") or "us-east-1").strip()
        api_base = _tts_api_base(self._config) or f"https://polly.{region}.amazonaws.com"
        url = _join_api_base(api_base, "/v1/speech")
        engine = _tts_model(self._config, default="neural")
        payload = {
            "Engine": engine,
            "OutputFormat": "mp3",
            "Text": text,
            "TextType": "text",
            "VoiceId": voice_id,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = _aws_sigv4_headers(
            method="POST",
            url=url,
            body=body,
            region=region,
            service="polly",
            access_key=access_key,
            secret_key=secret_key,
            content_type="application/json",
        )
        response = requests.post(url, data=body, headers=headers, timeout=_tts_timeout(self._config))
        _raise_for_tts_response(response, "Amazon Polly")
        return response.content

    def _request_elevenlabs(self, text: str, voice_id: str) -> bytes:
        api_key = _required_tts_api_key(self._config, "ElevenLabs TTS")
        api_base = _tts_api_base(self._config) or ELEVENLABS_TTS_API_BASE
        url = _join_api_base(api_base, f"/text-to-speech/{quote(voice_id, safe='')}?output_format=mp3_44100_128")
        payload = {
            "text": text,
            "model_id": _tts_model(self._config, default="eleven_multilingual_v2"),
        }
        response = requests.post(
            url,
            json=payload,
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
            timeout=_tts_timeout(self._config),
        )
        _raise_for_tts_response(response, "ElevenLabs TTS")
        return response.content


class VieNeuTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._server: VieNeuServerClient | None = None

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError("VieNeu-TTS không thể đọc văn bản rỗng.")

        voice_id = voice or self._config.tts_voice
        errors: list[str] = []
        for candidate in _vieneu_fallback_configs(self._config):
            try:
                self._synthesize_with_config(candidate, clean_text, output_path, voice_id)
                self._config = candidate
                return
            except Exception as exc:
                errors.append(f"{_vieneu_config_label(candidate)}: {_clean_message(exc)}")
                self._reset_server()

        details = "\n".join(errors[-4:])
        raise TTSError(f"VieNeu-TTS không chạy được sau khi tự hạ cấu hình.\n{details}")

    def _synthesize_with_config(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        voice_id = _compatible_vieneu_voice_id(config, voice_id)
        if self._should_use_subprocess(config):
            self._synthesize_subprocess(config, text, output_path, voice_id)
            return

        try:
            self._synthesize_in_process(config, text, output_path, voice_id)
        except Exception:
            if self._can_use_subprocess(config):
                self._synthesize_subprocess(config, text, output_path, voice_id)
                return
            raise

    def _synthesize_in_process(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        engine = _get_vieneu_engine(config)
        voice = _resolve_vieneu_preset_voice(engine, voice_id)
        infer_kwargs = _build_vieneu_infer_kwargs(
            engine=engine,
            text=text,
            voice=voice,
            temperature=config.vieneu_tts_temperature,
            max_chars=config.vieneu_tts_max_chars_chunk,
        )
        try:
            audio = engine.infer(**infer_kwargs)
            if _empty_vieneu_audio(audio):
                raise TTSError(_vieneu_empty_audio_message(config))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            engine.save(audio, str(output_path))
            if not output_path.exists() or output_path.stat().st_size <= 44:
                raise TTSError(_vieneu_empty_audio_message(config))
        except Exception as exc:
            raise TTSError(
                "VieNeu-TTS không tạo được audio "
                f"(mode={config.vieneu_tts_mode}, "
                f"voice={voice_id}, "
                f"device={config.vieneu_tts_device}): {exc}"
            ) from exc

    def _synthesize_subprocess(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        if self._server is None or self._server.config_key != _vieneu_server_config_key(config):
            self._server = _get_shared_vieneu_server(config)
        self._server.synthesize(
            text=text,
            voice=voice_id,
            output_path=output_path,
            temperature=config.vieneu_tts_temperature,
            max_chars=config.vieneu_tts_max_chars_chunk,
        )

    def _should_use_subprocess(self, config: AppConfig) -> bool:
        runtime = str(config.vieneu_tts_runtime or "auto").strip().lower()
        if runtime == "subprocess":
            return self._can_use_subprocess(config)
        return runtime == "auto" and self._can_use_subprocess(config)

    def _can_use_subprocess(self, config: AppConfig) -> bool:
        python = Path(config.vieneu_tts_python)
        return python.exists() and _vieneu_import_root(Path(config.vieneu_tts_path)).exists()

    def close(self) -> None:
        self._server = None

    def _reset_server(self) -> None:
        if self._server is not None:
            _discard_shared_vieneu_server(self._server)
            self._server = None


class VieNeuServerClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self.config_key = _vieneu_server_config_key(config)
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._output_queue: queue.Queue[str | None] = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def synthesize(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        temperature: float,
        max_chars: int,
    ) -> None:
        with self._lock:
            self._ensure_started()
            assert self._process is not None
            payload = {
                "op": "synthesize",
                "text": text,
                "voice": voice,
                "output": str(output_path),
                "temperature": temperature,
                "max_chars": max_chars,
            }
            self._write_payload(payload)
            response = self._read_response()
            if not response.get("ok"):
                raise TTSError(_clean_message(response.get("error") or "VieNeu subprocess failed."))

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        config = self._config
        mode = resolve_vieneu_effective_mode(
            config.vieneu_tts_core,
            config.vieneu_tts_mode,
            config.vieneu_tts_device,
        )
        device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
        model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
        backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
        _validate_vieneu_local_files(config, mode, model_name)
        script = Path(__file__).with_name("vieneu_tts_server.py")
        command = [
            str(Path(config.vieneu_tts_python)),
            str(script),
            "--root",
            str(Path(config.vieneu_tts_path)),
            "--mode",
            mode,
            "--api-base",
            str(config.vieneu_tts_api_base or ""),
            "--model-name",
            model_name,
            "--device",
            device,
            "--backend",
            backend,
        ]
        decoder_path = _effective_vieneu_decoder_path(config)
        encoder_path = _effective_vieneu_encoder_path(config)
        standard_codec_path = _effective_vieneu_standard_codec_path(config)
        if decoder_path:
            command.extend(["--decoder-path", str(Path(decoder_path))])
        if encoder_path:
            command.extend(["--encoder-path", str(Path(encoder_path))])
        if standard_codec_path:
            command.extend(["--standard-codec-path", str(Path(standard_codec_path))])
        if config.vieneu_tts_offline:
            command.append("--offline")
        env = os.environ.copy()
        if config.vieneu_tts_offline:
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
            env["HF_DATASETS_OFFLINE"] = "1"
        import_root = _vieneu_import_root(Path(config.vieneu_tts_path))
        env["PYTHONPATH"] = str(import_root) + os.pathsep + env.get("PYTHONPATH", "")
        self._process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._start_stdout_reader()
        response = self._read_response(timeout_seconds=300)
        if not response.get("ok"):
            raise TTSError(_clean_message(response.get("error") or "VieNeu subprocess init failed."))

    def _write_payload(self, payload: dict[str, Any]) -> None:
        assert self._process is not None
        assert self._process.stdin is not None
        if "text" in payload:
            payload = {**payload, "text": _clean_text(payload["text"])}
        line = json.dumps(payload, ensure_ascii=True) + "\n"
        self._process.stdin.write(line.encode("utf-8", errors="replace"))
        self._process.stdin.flush()

    def _read_response(self, timeout_seconds: float = 180) -> dict[str, Any]:
        assert self._process is not None
        deadline = time.monotonic() + timeout_seconds
        last_line = ""
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                line = self._output_queue.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if self._process.poll() is not None:
                    raise TTSError(
                        f"VieNeu subprocess exited early. Last output: {_clean_message(last_line.strip())}"
                    ) from None
                continue
            if not line:
                if self._process.poll() is not None:
                    raise TTSError(f"VieNeu subprocess exited early. Last output: {_clean_message(last_line.strip())}")
                continue
            last_line = line
            marker = "AI_PLAYER_JSON:"
            clean_line = line.replace("\x00", "")
            marker_index = clean_line.find(marker)
            if marker_index >= 0:
                payload_text = clean_line[marker_index + len(marker) :]
                try:
                    payload = json.loads(payload_text)
                except (TypeError, ValueError) as exc:
                    raise TTSError(
                        f"VieNeu subprocess returned invalid JSON. Last output: {_clean_message(last_line.strip())}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise TTSError(
                        "VieNeu subprocess returned invalid JSON payload. "
                        f"Last output: {_clean_message(last_line.strip())}"
                    )
                return payload
        self._terminate_current_process()
        raise TTSError(f"Timeout waiting for VieNeu subprocess. Last output: {_clean_message(last_line.strip())}")

    def _start_stdout_reader(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        self._output_queue = queue.Queue()

        def read_stdout() -> None:
            stdout = self._process.stdout if self._process is not None else None
            if stdout is None:
                self._output_queue.put(None)
                return
            try:
                for raw_line in iter(stdout.readline, b""):
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                    self._output_queue.put(line)
            finally:
                self._output_queue.put(None)

        self._reader_thread = threading.Thread(target=read_stdout, daemon=True)
        self._reader_thread.start()

    def _terminate_current_process(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                line = json.dumps({"op": "shutdown"}, ensure_ascii=True) + "\n"
                process.stdin.write(line.encode("utf-8"))
                process.stdin.flush()
            process.wait(timeout=5)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


def _get_shared_vieneu_server(config: AppConfig) -> VieNeuServerClient:
    key = _vieneu_server_config_key(config)
    with _VIENEU_SERVER_CACHE_LOCK:
        server = _VIENEU_SERVER_CACHE.get(key)
        if server is None:
            server = VieNeuServerClient(config)
            _VIENEU_SERVER_CACHE[key] = server
        return server


def _discard_shared_vieneu_server(server: VieNeuServerClient) -> None:
    with _VIENEU_SERVER_CACHE_LOCK:
        for key, cached in list(_VIENEU_SERVER_CACHE.items()):
            if cached is server:
                _VIENEU_SERVER_CACHE.pop(key, None)
    server.close()


def _close_shared_vieneu_servers() -> None:
    with _VIENEU_SERVER_CACHE_LOCK:
        servers = list(_VIENEU_SERVER_CACHE.values())
        _VIENEU_SERVER_CACHE.clear()
    for server in servers:
        server.close()


atexit.register(_close_shared_vieneu_servers)


def _vieneu_fallback_configs(config: AppConfig) -> list[AppConfig]:
    candidates: list[AppConfig] = [config]
    requested_mode = normalize_vieneu_mode(config.vieneu_tts_mode)
    effective_mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if effective_mode == "remote":
        return candidates
    cuda_available = _runtime_has_cuda()

    if requested_mode == "standard":
        if cuda_available:
            candidates.extend(
                [
                    replace(
                        config,
                        vieneu_tts_mode="standard",
                        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                        vieneu_tts_device="cuda",
                        vieneu_tts_backend="lmdeploy",
                    ),
                    replace(
                        config,
                        vieneu_tts_mode="standard",
                        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                        vieneu_tts_device="cuda",
                        vieneu_tts_backend="native",
                    ),
                ]
            )
        candidates.append(
            replace(
                config,
                vieneu_tts_mode="standard",
                vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                vieneu_tts_device="cpu",
                vieneu_tts_backend="native",
            )
        )

    if cuda_available:
        candidates.append(
            replace(
                config,
                vieneu_tts_mode="turbo",
                vieneu_tts_model_name=INTERNAL_VIENEU_TURBO_GGUF,
                vieneu_tts_device="cuda",
                vieneu_tts_backend="native",
            )
        )
    candidates.append(
        replace(
            config,
            vieneu_tts_mode="turbo",
            vieneu_tts_model_name=INTERNAL_VIENEU_TURBO_GGUF,
            vieneu_tts_device="cpu",
            vieneu_tts_backend="native",
        )
    )
    return _unique_vieneu_configs(candidates)


def _unique_vieneu_configs(configs: list[AppConfig]) -> list[AppConfig]:
    unique: list[AppConfig] = []
    seen: set[tuple[str, ...]] = set()
    for config in configs:
        key = _vieneu_server_config_key(config)
        if key in seen:
            continue
        seen.add(key)
        unique.append(config)
    return unique


def _vieneu_server_config_key(config: AppConfig) -> tuple[str, ...]:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
    backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
    return (
        mode,
        device,
        backend,
        model_name,
        str(config.vieneu_tts_api_base or ""),
        str(Path(_effective_vieneu_decoder_path(config))),
        str(Path(_effective_vieneu_encoder_path(config))),
        str(Path(_effective_vieneu_standard_codec_path(config))),
        str(config.vieneu_tts_runtime),
        str(config.vieneu_tts_offline),
    )


def _vieneu_config_label(config: AppConfig) -> str:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
    backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
    return f"mode={mode}, device={device}, backend={backend}"


def _compatible_vieneu_voice_id(config: AppConfig, voice_id: str) -> str:
    voices = available_voices("vieneu", config)
    choices = tuple((voice.name, voice.id) for voice in voices)
    migrated = migrate_vieneu_legacy_voice_id(voice_id, choices)
    available_ids = {voice.id for voice in voices}
    if migrated in available_ids:
        return migrated
    gender = voice_gender("vieneu", voice_id)
    if gender in {"male", "female"}:
        for preferred in _preferred_voice_ids("vieneu", config, gender):
            if preferred in available_ids:
                return preferred
        for voice in voices:
            if voice_gender("vieneu", voice.id) == gender:
                return voice.id
    return voices[0].id if voices else voice_id


def _runtime_has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _get_vieneu_engine(config: AppConfig):
    root = Path(config.vieneu_tts_path)
    import_root = _vieneu_import_root(root)
    if import_root.exists() and str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

    selected_mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, selected_mode)
    _validate_vieneu_local_files(config, selected_mode, model_name)
    backend = resolve_vieneu_runtime_backend(
        selected_mode,
        model_name,
        device,
        config.vieneu_tts_backend,
    )
    api_base = str(config.vieneu_tts_api_base or "").strip()
    if selected_mode != "remote":
        api_base = ""
    decoder_path = _effective_vieneu_decoder_path(config)
    encoder_path = _effective_vieneu_encoder_path(config)
    standard_codec_path = _effective_vieneu_standard_codec_path(config)

    cache_key = (
        str(root.resolve()) if root.exists() else str(root),
        selected_mode,
        api_base,
        model_name,
        str(Path(decoder_path)) if decoder_path else "",
        str(Path(encoder_path)) if encoder_path else "",
        str(Path(standard_codec_path)) if standard_codec_path else "",
        device,
        backend,
    )
    cached = _VIENEU_ENGINE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _VIENEU_ENGINE_LOCK:
        cached = _VIENEU_ENGINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            from vieneu import Vieneu
        except ImportError as exc:
            raise TTSError(
                "Không import được VieNeu-TTS nội bộ. Chạy "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt "
                "để cài dependency, rồi chạy scripts\\download_vieneu_tts_models.ps1 nếu thiếu model."
            ) from exc

        kwargs = _build_vieneu_engine_kwargs(
            mode=selected_mode,
            api_base=api_base,
            model_name=model_name,
            decoder_path=_effective_vieneu_decoder_path(config),
            encoder_path=_effective_vieneu_encoder_path(config),
            standard_codec_path=_effective_vieneu_standard_codec_path(config),
            device=device,
            backend=backend,
        )
        offline_env = push_hf_offline_environment(config.vieneu_tts_offline)
        try:
            engine = Vieneu(mode=selected_mode, **kwargs)
        except Exception as exc:
            raise TTSError(
                "Không khởi tạo được VieNeu-TTS "
                f"(mode={selected_mode}, model={model_name}, device={device}, backend={backend}): {exc}"
            ) from exc
        finally:
            pop_hf_offline_environment(offline_env)
        _VIENEU_ENGINE_CACHE[cache_key] = engine
        return engine


def _build_vieneu_engine_kwargs(
    *,
    mode: str,
    api_base: str,
    model_name: str,
    device: str,
    backend: str,
    decoder_path: str = "",
    encoder_path: str = "",
    standard_codec_path: str = "",
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if mode == "remote":
        if api_base:
            kwargs["api_base"] = api_base
        if model_name:
            kwargs["model_name"] = model_name
        kwargs["codec_repo"] = _VIENEU_REMOTE_CODEC_REPO
        kwargs["codec_device"] = "cpu"
        return kwargs

    if model_name:
        kwargs["backbone_repo"] = _resolve_local_gguf_if_dir(model_name)

    runtime_device = "cuda" if device == "cuda" else "cpu"
    if mode == "standard":
        kwargs["backbone_device"] = runtime_device
        kwargs["codec_device"] = runtime_device
        if standard_codec_path:
            kwargs["codec_repo"] = _resolve_existing_dir(standard_codec_path)
    else:
        if decoder_path:
            kwargs["decoder_repo"] = _resolve_existing_file(decoder_path)
        if encoder_path:
            kwargs["encoder_repo"] = _resolve_existing_file(encoder_path)
        kwargs["device"] = runtime_device
        if mode in {"fast", "turbo_gpu"} and backend:
            kwargs["backend"] = backend
    return kwargs


def _resolve_vieneu_model_name(value: object, mode: str) -> str:
    clean = str(value or "").strip()
    if clean:
        return clean
    if mode == "standard":
        return "pnnbao-ump/VieNeu-TTS"
    if mode == "remote":
        return "pnnbao-ump/VieNeu-TTS"
    return "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"


def _resolve_local_gguf_if_dir(model_name: str) -> str:
    path = Path(model_name)
    if not path.exists() or not path.is_dir():
        return model_name
    candidates = sorted(
        [item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".gguf"],
        key=lambda item: item.name.lower(),
    )
    return str(candidates[0].resolve()) if candidates else model_name


def _resolve_existing_file(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_file() else value


def _resolve_existing_dir(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_dir() else value


def _effective_vieneu_decoder_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_decoder_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_TURBO_DECODER if Path(INTERNAL_VIENEU_TURBO_DECODER).exists() else configured


def _effective_vieneu_encoder_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_encoder_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_TURBO_ENCODER if Path(INTERNAL_VIENEU_TURBO_ENCODER).exists() else configured


def _effective_vieneu_standard_codec_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_standard_codec_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_STANDARD_CODEC if Path(INTERNAL_VIENEU_STANDARD_CODEC).exists() else configured


def _local_vieneu_standard_models() -> list[VieNeuModelOption]:
    standard_dir = INTERNAL_VIENEU_STANDARD_PATH
    if not standard_dir.exists():
        return []
    models: list[VieNeuModelOption] = []
    for path in sorted(standard_dir.glob("*.gguf"), key=lambda item: item.name.lower()):
        models.append(VieNeuModelOption(str(path.resolve()), f"{path.stem} (local offline)", True))
    return models


def _local_vieneu_turbo_models() -> list[VieNeuModelOption]:
    turbo_dir = INTERNAL_VIENEU_TURBO_PATH
    if not turbo_dir.exists():
        return []
    return [
        VieNeuModelOption(str(path.resolve()), f"{path.stem} (local offline)", True)
        for path in sorted(turbo_dir.glob("*.gguf"), key=lambda item: item.name.lower())
    ]


def _unique_vieneu_models(models: list[VieNeuModelOption]) -> list[VieNeuModelOption]:
    seen: set[str] = set()
    unique: list[VieNeuModelOption] = []
    for model in models:
        if model.id in seen:
            continue
        seen.add(model.id)
        unique.append(model)
    return unique


def _validate_vieneu_local_files(config: AppConfig, mode: str, model_name: str) -> None:
    if mode == "remote" or not config.vieneu_tts_offline:
        return

    required = [("model", model_name)]
    if mode != "standard":
        required.extend(
            [
                ("decoder", _effective_vieneu_decoder_path(config)),
                ("encoder", _effective_vieneu_encoder_path(config)),
            ]
        )
    else:
        required.append(
            (
                "standard codec",
                str(Path(_effective_vieneu_standard_codec_path(config)) / "pytorch_model.bin"),
            )
        )

    missing = [f"{label}: {path}" for label, path in required if path and not Path(path).exists()]
    if missing:
        details = "\n".join(missing)
        raise TTSError(
            "Thiếu file VieNeu-TTS offline. Chạy scripts\\download_vieneu_tts_models.ps1 "
            f"để tải đầy đủ model/cache.\n{details}"
        )


def _build_vieneu_infer_kwargs(
    *,
    engine: Any,
    text: str,
    voice: Any,
    temperature: float,
    max_chars: int,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "text": text,
        "voice": voice,
        "temperature": _finite_float(temperature, default=0.6),
        "max_chars": _int_value(max_chars, default=160, minimum=1),
    }
    infer = getattr(engine, "infer", None)
    try:
        signature = inspect.signature(infer) if callable(infer) else None
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return {key: value for key, value in kwargs.items() if value is not None}
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return {key: value for key, value in kwargs.items() if value is not None}
    return {key: value for key, value in kwargs.items() if key in signature.parameters and value is not None}


def _empty_vieneu_audio(audio: object) -> bool:
    size = getattr(audio, "size", None)
    if size is not None:
        try:
            return int(size) <= 0
        except (TypeError, ValueError, OverflowError):
            pass
    try:
        return len(audio) <= 0  # type: ignore[arg-type]
    except Exception:
        return audio is None


def _vieneu_empty_audio_message(config: AppConfig) -> str:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode == "remote":
        api_base = str(config.vieneu_tts_api_base or "http://localhost:23333/v1")
        return f"VieNeu remote API không trả về audio. Kiểm tra server/API tại {api_base}."
    return "VieNeu-TTS trả về audio rỗng."


def _resolve_vieneu_preset_voice(engine: Any, voice_id: str) -> Any | None:
    raw = str(voice_id or "").strip()
    if not raw:
        return None
    try:
        return engine.get_preset_voice(raw)
    except Exception:
        pass

    try:
        available = tuple(engine.list_preset_voices() or ())
    except Exception:
        available = tuple()
    migrated = migrate_vieneu_legacy_voice_id(raw, available)
    if migrated and migrated != raw:
        return engine.get_preset_voice(migrated)

    normalized = _normalize_voice_token(raw)
    for label, preset_id in available:
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if normalized in {
            _normalize_voice_token(clean_id),
            _normalize_voice_token(clean_label),
            _normalize_voice_token(clean_label.split("(", 1)[0].strip()),
        }:
            return engine.get_preset_voice(clean_id)

    available_ids = ", ".join(str(preset_id) for _label, preset_id in available)
    raise TTSError(f"Không tìm thấy voice VieNeu {voice_id!r}. Các voice hiện có: {available_ids or '(trống)'}")


def _tts_cache_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_TTS_CACHE", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _tts_cache_lock_for(cache_path: Path) -> threading.Lock:
    normalized_path = cache_path.absolute()
    with _TTS_CACHE_LOCK:
        lock = _TTS_CACHE_KEY_LOCKS.get(normalized_path)
        if lock is None:
            lock = threading.Lock()
            _TTS_CACHE_KEY_LOCKS[normalized_path] = lock
        return lock


def _tts_cache_path(provider: str, config: AppConfig, text: str, voice: str, output_path: Path) -> Path:
    suffix = output_path.suffix.lower() or f".{tts_output_suffix(provider)}"
    payload = {
        "version": 1,
        "provider": normalize_tts_provider(provider),
        "text": _cache_text(text),
        "voice": str(voice or ""),
        "tts_api_base": str(getattr(config, "tts_api_base", "")),
        "tts_api_region": str(getattr(config, "tts_api_region", "")),
        "tts_model": str(getattr(config, "tts_model", "")),
        "tts_timeout": _finite_float(getattr(config, "tts_timeout_seconds", 30.0), default=30.0),
        "vieneu_core": str(config.vieneu_tts_core),
        "vieneu_mode": str(config.vieneu_tts_mode),
        "vieneu_model": str(config.vieneu_tts_model_name),
        "vieneu_decoder": str(config.vieneu_tts_decoder_path),
        "vieneu_encoder": str(config.vieneu_tts_encoder_path),
        "vieneu_codec": str(config.vieneu_tts_standard_codec_path),
        "vieneu_device": str(config.vieneu_tts_device),
        "vieneu_backend": str(config.vieneu_tts_backend),
        "vieneu_temperature": _finite_float(config.vieneu_tts_temperature, default=0.6),
        "vieneu_max_chars": _int_value(config.vieneu_tts_max_chars_chunk, default=160, minimum=1),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return RUNTIME_DIR / "tts-cache" / f"{digest}{suffix}"


def _cache_text(value: object) -> str:
    text = _clean_text(value)
    text = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _finite_float(value: object, *, default: float) -> float:
    return _core_finite_float(value, default=default)


def _int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)


def _preferred_voice_ids(provider: str, config: AppConfig, gender: str) -> tuple[str, ...]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "edge":
        return ("vi-VN-NamMinhNeural",) if gender == "male" else ("vi-VN-HoaiMyNeural",)
    if normalized_provider in ONLINE_TTS_PROVIDERS:
        return (_preferred_online_voice_id(normalized_provider, gender),)

    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode in {"standard", "remote"}:
        return ("Vinh", "Binh", "Tuyen") if gender == "male" else ("Doan", "Ngoc", "Ly")
    return (
        ("Xuân Vĩnh", "Phạm Tuyên", "Xuan Vinh", "Pham Tuyen")
        if gender == "male"
        else ("Thục Đoan", "Bích Ngọc", "Thuc Doan", "Bich Ngoc")
    )


def _clean_message(value: object) -> str:
    return _core_clean_message(value)


def _clean_text(value: object) -> str:
    return _core_clean_text(value)


def _tts_api_base(config: AppConfig) -> str:
    return str(getattr(config, "tts_api_base", "") or "").strip().rstrip("/")


def _tts_model(config: AppConfig, *, default: str) -> str:
    return str(getattr(config, "tts_model", "") or default).strip() or default


def _tts_timeout(config: AppConfig) -> float:
    return max(1.0, _finite_float(getattr(config, "tts_timeout_seconds", 30.0), default=30.0))


def _required_tts_api_key(config: AppConfig, provider_name: str) -> str:
    api_key = str(getattr(config, "tts_api_key", "") or "").strip()
    if not api_key:
        raise TTSError(f"{provider_name} requires tts_api_key.")
    return api_key


def _required_tts_api_secret(config: AppConfig, provider_name: str) -> str:
    api_secret = str(getattr(config, "tts_api_secret", "") or "").strip()
    if not api_secret:
        raise TTSError(f"{provider_name} requires tts_api_secret.")
    return api_secret


def _voice_language_code(voice_id: str, *, default: str) -> str:
    parts = str(voice_id or "").strip().split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return default


def _google_tts_url(api_base: str, api_key: str) -> str:
    separator = "&" if "?" in api_base else "?"
    return f"{api_base}{separator}key={quote(api_key, safe='')}"


def _join_api_base(api_base: str, path: str) -> str:
    base = str(api_base or "").strip().rstrip("/")
    clean_path = "/" + str(path or "").lstrip("/")
    return f"{base}{clean_path}"


def _response_json(response: requests.Response, provider_name: str) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise TTSError(f"{provider_name} returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise TTSError(f"{provider_name} returned an invalid JSON payload.")
    return data


def _raise_for_tts_response(response: requests.Response, provider_name: str) -> None:
    if response.status_code < 400:
        return
    detail = ""
    try:
        data = response.json()
        detail = json.dumps(data, ensure_ascii=False)[:500]
    except Exception:
        detail = str(getattr(response, "text", "") or "")[:500]
    raise TTSError(f"{provider_name} request failed with HTTP {response.status_code}: {detail}")


def _write_tts_audio(output_path: Path, audio: bytes) -> None:
    if not audio:
        raise TTSError("TTS provider returned empty audio.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)


def _aws_sigv4_headers(
    *,
    method: str,
    url: str,
    body: bytes,
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    content_type: str,
) -> dict[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_querystring = parsed.query
    now = _datetime.datetime.now(_datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-date"
    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _aws_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-Amz-Date": amz_date,
    }


def _aws_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    date_key = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _remove_tts_output(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _vieneu_import_root(root: Path) -> Path:
    if (root / "src" / "vieneu").exists():
        return root / "src"
    if (root / "vieneu").exists():
        return root
    bundled = Path(INTERNAL_VIENEU_TTS_PATH)
    if (bundled / "vieneu").exists():
        return bundled
    return root


def _vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    if config is None:
        return STANDARD_VIENEU_VOICES

    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode == "remote":
        return STANDARD_VIENEU_VOICES
    model_voices_path = _vieneu_model_voices_path(config.vieneu_tts_model_name)
    if model_voices_path.is_file():
        voices = _read_vieneu_voices(model_voices_path)
        if voices:
            return voices

    if mode == "standard":
        import_root = _vieneu_import_root(Path(config.vieneu_tts_path))
        voices_path = import_root / "vieneu" / "assets" / "voices.json"
        if voices_path.is_file():
            voices = _read_vieneu_voices(voices_path)
            if voices:
                return voices

    return STANDARD_VIENEU_VOICES if mode in {"standard", "remote"} else TURBO_VIENEU_VOICES
