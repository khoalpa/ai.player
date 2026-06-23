from __future__ import annotations

from ai_player.core.config import AppConfig
from ai_player.services import tts_vieneu as _tts_vieneu
from ai_player.services.tts_base import (
    ONLINE_TTS_PROVIDERS,
    BaseTTSProvider,
    CachedTTSProvider,
    NoTTSProvider,
    TTSError,
    _cache_text,
    _tts_cache_path,
    available_tts_providers,
    available_vieneu_modes,
    is_non_speech_tts_text,
    is_online_tts_provider,
    is_pathological_tts_duration,
    normalize_tts_provider,
    prepare_tts_text,
    tts_output_suffix,
)
from ai_player.services.tts_edge import EdgeTTSProvider
from ai_player.services.tts_edge import compatible_edge_voice_id as _compatible_edge_voice_id
from ai_player.services.tts_online import OnlineTTSProvider
from ai_player.services.tts_online import compatible_online_voice_id as _compatible_online_voice_id
from ai_player.services.tts_online import preferred_online_voice_id as _preferred_online_voice_id
from ai_player.services.tts_vieneu import (
    VieNeuServerClient,
    VieNeuTTSProvider,
    available_vieneu_models,
    normalize_vieneu_backend,
    normalize_vieneu_device,
    normalize_vieneu_mode,
    resolve_vieneu_effective_mode,
    resolve_vieneu_runtime_backend,
    resolve_vieneu_runtime_device,
)
from ai_player.services.tts_voices import (
    AMAZON_POLLY_VOICES,
    AZURE_TTS_VOICES,
    EDGE_VOICES,
    GOOGLE_TTS_VOICES,
    VieNeuModelOption,
    VoiceOption,
    migrate_vieneu_legacy_voice_id,
)
from ai_player.services.tts_voices import voice_gender as _catalog_voice_gender

__all__ = (
    "AMAZON_POLLY_VOICES",
    "AZURE_TTS_VOICES",
    "BaseTTSProvider",
    "CachedTTSProvider",
    "EDGE_VOICES",
    "EdgeTTSProvider",
    "GOOGLE_TTS_VOICES",
    "NoTTSProvider",
    "ONLINE_TTS_PROVIDERS",
    "OnlineTTSProvider",
    "TTSError",
    "VieNeuModelOption",
    "VieNeuServerClient",
    "VieNeuTTSProvider",
    "VoiceOption",
    "_build_vieneu_engine_kwargs",
    "_build_vieneu_infer_kwargs",
    "_cache_text",
    "_compatible_edge_voice_id",
    "_compatible_online_voice_id",
    "_compatible_vieneu_voice_id",
    "_discard_shared_vieneu_server",
    "_effective_vieneu_decoder_path",
    "_effective_vieneu_encoder_path",
    "_effective_vieneu_standard_codec_path",
    "_empty_vieneu_audio",
    "_get_shared_vieneu_server",
    "_get_vieneu_engine",
    "_preferred_voice_ids",
    "_resolve_vieneu_model_name",
    "_resolve_vieneu_preset_voice",
    "_runtime_has_cuda",
    "_tts_cache_path",
    "_validate_vieneu_local_files",
    "_vieneu_config_label",
    "_vieneu_empty_audio_message",
    "_vieneu_fallback_configs",
    "_vieneu_import_root",
    "_vieneu_server_config_key",
    "_vieneu_voices",
    "available_tts_providers",
    "available_vieneu_models",
    "available_vieneu_modes",
    "available_voices",
    "create_tts_provider",
    "is_non_speech_tts_text",
    "is_online_tts_provider",
    "is_pathological_tts_duration",
    "normalize_tts_provider",
    "normalize_vieneu_backend",
    "normalize_vieneu_device",
    "normalize_vieneu_mode",
    "prepare_tts_text",
    "resolve_vieneu_effective_mode",
    "resolve_vieneu_runtime_backend",
    "resolve_vieneu_runtime_device",
    "select_voice_for_gender",
    "tts_output_suffix",
    "voice_gender",
)

_build_vieneu_engine_kwargs = _tts_vieneu._build_vieneu_engine_kwargs
_build_vieneu_infer_kwargs = _tts_vieneu._build_vieneu_infer_kwargs
_compatible_vieneu_voice_id = _tts_vieneu._compatible_vieneu_voice_id
_effective_vieneu_decoder_path = _tts_vieneu._effective_vieneu_decoder_path
_effective_vieneu_encoder_path = _tts_vieneu._effective_vieneu_encoder_path
_effective_vieneu_standard_codec_path = _tts_vieneu._effective_vieneu_standard_codec_path
_empty_vieneu_audio = _tts_vieneu._empty_vieneu_audio
_get_shared_vieneu_server = _tts_vieneu._get_shared_vieneu_server
_get_vieneu_engine = _tts_vieneu._get_vieneu_engine
_discard_shared_vieneu_server = _tts_vieneu._discard_shared_vieneu_server
_resolve_vieneu_model_name = _tts_vieneu._resolve_vieneu_model_name
_resolve_vieneu_preset_voice = _tts_vieneu._resolve_vieneu_preset_voice
_runtime_has_cuda = _tts_vieneu._runtime_has_cuda
_validate_vieneu_local_files = _tts_vieneu._validate_vieneu_local_files
_vieneu_config_label = _tts_vieneu._vieneu_config_label
_vieneu_empty_audio_message = _tts_vieneu._vieneu_empty_audio_message
_vieneu_fallback_configs = _tts_vieneu._vieneu_fallback_configs
_vieneu_import_root = _tts_vieneu._vieneu_import_root
_vieneu_server_config_key = _tts_vieneu._vieneu_server_config_key


def available_voices(provider: str, config: AppConfig | None = None) -> list[VoiceOption]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "none":
        return [VoiceOption("none", "Kh\u00f4ng TTS")]
    if normalized_provider == "vieneu":
        return _tts_vieneu.vieneu_voices(config)
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


def _preferred_voice_ids(provider: str, config: AppConfig, gender: str) -> tuple[str, ...]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "edge":
        return ("vi-VN-NamMinhNeural",) if gender == "male" else ("vi-VN-HoaiMyNeural",)
    if normalized_provider in ONLINE_TTS_PROVIDERS:
        return (_preferred_online_voice_id(normalized_provider, gender),)
    return _tts_vieneu._preferred_vieneu_voice_ids(config, gender)


def _vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    return _tts_vieneu.vieneu_voices(config)
