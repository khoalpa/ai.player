from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time as time
import unicodedata
from pathlib import Path

from ai_player.core.config import (
    INTERNAL_VIENEU_STANDARD_CODEC,
    INTERNAL_VIENEU_STANDARD_GGUF,
    INTERNAL_VIENEU_STANDARD_PATH,
    INTERNAL_VIENEU_TTS_PATH,
    INTERNAL_VIENEU_TURBO_DECODER,
    INTERNAL_VIENEU_TURBO_ENCODER,
    INTERNAL_VIENEU_TURBO_GGUF,
    INTERNAL_VIENEU_TURBO_PATH,
    RUNTIME_DIR,
    AppConfig,
)
from ai_player.services import tts_edge as _tts_edge
from ai_player.services import tts_online as _tts_online
from ai_player.services import tts_vieneu as _tts_vieneu
from ai_player.services.tts_base import (
    ONLINE_TTS_PROVIDERS,
    BaseTTSProvider,
    NoTTSProvider,
    normalize_tts_provider,
)
from ai_player.services.tts_base import (
    TTSError as TTSError,
)
from ai_player.services.tts_base import (
    clean_text as _clean_text,
)
from ai_player.services.tts_base import (
    finite_float as _finite_float,
)
from ai_player.services.tts_base import (
    int_value as _int_value,
)
from ai_player.services.tts_edge import EdgeTTSProvider
from ai_player.services.tts_online import OnlineTTSProvider
from ai_player.services.tts_voices import (
    AMAZON_POLLY_VOICES,
    AZURE_TTS_VOICES,
    EDGE_VOICES,
    GOOGLE_TTS_VOICES,
    VieNeuModelOption,
    VoiceOption,
    available_tts_provider_options,
    available_vieneu_mode_options,
    migrate_vieneu_legacy_voice_id,
)
from ai_player.services.tts_voices import voice_gender as _catalog_voice_gender

edge_tts = _tts_edge.edge_tts
requests = _tts_online.requests
_compatible_edge_voice_id = _tts_edge.compatible_edge_voice_id
_compatible_online_voice_id = _tts_online.compatible_online_voice_id
_preferred_online_voice_id = _tts_online.preferred_online_voice_id
VieNeuServerClient = _tts_vieneu.VieNeuServerClient
normalize_vieneu_backend = _tts_vieneu.normalize_vieneu_backend
normalize_vieneu_device = _tts_vieneu.normalize_vieneu_device
normalize_vieneu_mode = _tts_vieneu.normalize_vieneu_mode
resolve_vieneu_effective_mode = _tts_vieneu.resolve_vieneu_effective_mode
resolve_vieneu_runtime_backend = _tts_vieneu.resolve_vieneu_runtime_backend
resolve_vieneu_runtime_device = _tts_vieneu.resolve_vieneu_runtime_device

_TTS_CACHE_LOCK = threading.Lock()
_TTS_CACHE_KEY_LOCKS: dict[Path, threading.Lock] = {}


_RUNTIME_HOOK_DEFAULTS = {
    "INTERNAL_VIENEU_STANDARD_CODEC": INTERNAL_VIENEU_STANDARD_CODEC,
    "INTERNAL_VIENEU_STANDARD_GGUF": INTERNAL_VIENEU_STANDARD_GGUF,
    "INTERNAL_VIENEU_STANDARD_PATH": INTERNAL_VIENEU_STANDARD_PATH,
    "INTERNAL_VIENEU_TTS_PATH": INTERNAL_VIENEU_TTS_PATH,
    "INTERNAL_VIENEU_TURBO_DECODER": INTERNAL_VIENEU_TURBO_DECODER,
    "INTERNAL_VIENEU_TURBO_ENCODER": INTERNAL_VIENEU_TURBO_ENCODER,
    "INTERNAL_VIENEU_TURBO_GGUF": INTERNAL_VIENEU_TURBO_GGUF,
    "INTERNAL_VIENEU_TURBO_PATH": INTERNAL_VIENEU_TURBO_PATH,
}
_RUNTIME_HOOK_NAMES = (
    *_RUNTIME_HOOK_DEFAULTS,
    "_get_shared_vieneu_server",
    "_discard_shared_vieneu_server",
    "_runtime_has_cuda",
    "_get_vieneu_engine",
)

_get_shared_vieneu_server = _tts_vieneu._get_shared_vieneu_server
_discard_shared_vieneu_server = _tts_vieneu._discard_shared_vieneu_server
_runtime_has_cuda = _tts_vieneu._runtime_has_cuda
_get_vieneu_engine = _tts_vieneu._get_vieneu_engine


def _sync_vieneu_module_overrides() -> None:
    for name in _RUNTIME_HOOK_NAMES:
        setattr(_tts_vieneu, name, globals()[name])

def available_tts_providers() -> list[VoiceOption]:
    return available_tts_provider_options()


def available_vieneu_modes() -> list[VoiceOption]:
    return available_vieneu_mode_options()

def available_vieneu_models(mode: str, config: AppConfig) -> list[VieNeuModelOption]:
    _sync_vieneu_module_overrides()
    return _tts_vieneu.available_vieneu_models(mode, config)


class VieNeuTTSProvider(_tts_vieneu.VieNeuTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        _sync_vieneu_module_overrides()
        super().__init__(config)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        _sync_vieneu_module_overrides()
        super().synthesize(text, output_path, voice=voice)

    def _synthesize_with_config(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        _sync_vieneu_module_overrides()
        super()._synthesize_with_config(config, text, output_path, voice_id)

    def _synthesize_in_process(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        _sync_vieneu_module_overrides()
        super()._synthesize_in_process(config, text, output_path, voice_id)

    def _synthesize_subprocess(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        _sync_vieneu_module_overrides()
        super()._synthesize_subprocess(config, text, output_path, voice_id)


def _vieneu_fallback_configs(config: AppConfig) -> list[AppConfig]:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._vieneu_fallback_configs(config)


def _vieneu_server_config_key(config: AppConfig) -> tuple[str, ...]:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._vieneu_server_config_key(config)


def _vieneu_config_label(config: AppConfig) -> str:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._vieneu_config_label(config)


def _compatible_vieneu_voice_id(config: AppConfig, voice_id: str) -> str:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._compatible_vieneu_voice_id(config, voice_id)


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
) -> dict[str, object]:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._build_vieneu_engine_kwargs(
        mode=mode,
        api_base=api_base,
        model_name=model_name,
        decoder_path=decoder_path,
        encoder_path=encoder_path,
        standard_codec_path=standard_codec_path,
        device=device,
        backend=backend,
    )


def _resolve_vieneu_model_name(value: object, mode: str) -> str:
    return _tts_vieneu._resolve_vieneu_model_name(value, mode)


def _effective_vieneu_decoder_path(config: AppConfig) -> str:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._effective_vieneu_decoder_path(config)


def _effective_vieneu_encoder_path(config: AppConfig) -> str:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._effective_vieneu_encoder_path(config)


def _effective_vieneu_standard_codec_path(config: AppConfig) -> str:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._effective_vieneu_standard_codec_path(config)


def _validate_vieneu_local_files(config: AppConfig, mode: str, model_name: str) -> None:
    _sync_vieneu_module_overrides()
    _tts_vieneu._validate_vieneu_local_files(config, mode, model_name)


def _build_vieneu_infer_kwargs(
    *,
    engine: object,
    text: str,
    voice: object,
    temperature: float,
    max_chars: int,
) -> dict[str, object]:
    return _tts_vieneu._build_vieneu_infer_kwargs(
        engine=engine,
        text=text,
        voice=voice,
        temperature=temperature,
        max_chars=max_chars,
    )


def _empty_vieneu_audio(audio: object) -> bool:
    return _tts_vieneu._empty_vieneu_audio(audio)


def _vieneu_empty_audio_message(config: AppConfig) -> str:
    return _tts_vieneu._vieneu_empty_audio_message(config)


def _resolve_vieneu_preset_voice(engine: object, voice_id: str) -> object | None:
    return _tts_vieneu._resolve_vieneu_preset_voice(engine, voice_id)


def _vieneu_import_root(root: Path) -> Path:
    _sync_vieneu_module_overrides()
    return _tts_vieneu._vieneu_import_root(root)


def _vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    _sync_vieneu_module_overrides()
    return _tts_vieneu.vieneu_voices(config)

def available_voices(provider: str, config: AppConfig | None = None) -> list[VoiceOption]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "none":
        return [VoiceOption("none", "Kh\u00f4ng TTS")]
    if normalized_provider == "vieneu":
        return _vieneu_voices(config)
    if normalized_provider == "azure_tts":
        return AZURE_TTS_VOICES
    if normalized_provider == "google_tts":
        return GOOGLE_TTS_VOICES
    if normalized_provider == "amazon_polly":
        return AMAZON_POLLY_VOICES
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


def create_tts_provider(config: AppConfig) -> BaseTTSProvider:
    provider = normalize_tts_provider(config.tts_provider)
    if provider == "none":
        return NoTTSProvider(config)
    if provider == "vieneu":
        return CachedTTSProvider(VieNeuTTSProvider(config), config, provider)
    if provider in ONLINE_TTS_PROVIDERS:
        return CachedTTSProvider(OnlineTTSProvider(config, provider), config, provider)
    return CachedTTSProvider(EdgeTTSProvider(config), config, provider)

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
    normalized = normalized.replace("\u0111", "d")
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
        ("Xu\u00e2n V\u0129nh", "Ph\u1ea1m Tuy\u00ean", "Xuan Vinh", "Pham Tuyen")
        if gender == "male"
        else ("Th\u1ee5c \u0110oan", "B\u00edch Ng\u1ecdc", "Thuc Doan", "Bich Ngoc")
    )


