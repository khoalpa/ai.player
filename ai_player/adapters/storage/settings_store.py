from __future__ import annotations

import json
import math
import os
from dataclasses import fields, replace
from typing import Any

from ai_player.adapters.storage.atomic import write_text_atomic
from ai_player.adapters.storage.secret_store import SecretStoreError, protect_text, reveal_text
from ai_player.configuration import (
    CONFIG_DIR,
    DEFAULT_OCR_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_PATH,
    LOCAL_WHISPER_MODEL_PATH,
    AppConfig,
    preserved_english_terms_file_path,
    preserved_source_terms_file_path,
    read_preserved_source_terms_file,
)
from ai_player.configuration.schema import CURRENT_SCHEMA_VERSION, migrate_settings
from ai_player.core.app_logging import get_logger

SETTINGS_FILE = CONFIG_DIR / "settings.json"
TELEGRAM_BLACKLIST_FILENAME = "telegram_blacklist.json"
SECRETS_FILENAME = "secrets.json"
ONLINE_USER_CONFIG_FILENAME = "online_providers.local.json"
RUNTIME_LOCAL_FILENAME = "runtime.local.json"
RECENT_SOURCES_FILENAME = "recent_sources.json"
TELEGRAM_STATE_FILENAME = "telegram_state.json"
LOGGER = get_logger(__name__)
SESSION_ONLY_DEFAULTS = {
    "audio_source": "original",
    "transcript_path": "",
    "dubbing_enabled_by_default": False,
    "preserved_source_terms": "",
    "preserved_english_terms": "",
    "preserved_source_terms_file": str(preserved_source_terms_file_path()),
    "preserved_english_terms_file": str(preserved_english_terms_file_path()),
}
SECRET_SETTINGS = {
    "asr_api_key",
    "transcript_cleanup_api_key",
    "translator_api_key",
    "tts_api_key",
    "tts_api_secret",
    "speaker_gender_api_key",
    "ocr_api_key",
}
SECRET_PAYLOAD_KEYS = {
    "asr_api_key": "asr_api_key_secret",
    "transcript_cleanup_api_key": "transcript_cleanup_api_key_secret",
    "translator_api_key": "translator_api_key_secret",
    "tts_api_key": "tts_api_key_secret",
    "tts_api_secret": "tts_api_secret_secret",
    "speaker_gender_api_key": "speaker_gender_api_key_secret",
    "ocr_api_key": "ocr_api_key_secret",
}
ASR_API_KEY_SECRET_MAP_KEY = "asr_api_key_secrets"
PROVIDER_SECRET_MAP_KEYS = {
    "asr_api_key": ASR_API_KEY_SECRET_MAP_KEY,
    "transcript_cleanup_api_key": "transcript_cleanup_api_key_secrets",
    "translator_api_key": "translator_api_key_secrets",
    "tts_api_key": "tts_api_key_secrets",
    "tts_api_secret": "tts_api_secret_secrets",
    "speaker_gender_api_key": "speaker_gender_api_key_secrets",
    "ocr_api_key": "ocr_api_key_secrets",
}
PROVIDER_SETTING_KEYS = {
    "asr_api_key": "asr_provider",
    "transcript_cleanup_api_key": "transcript_cleanup_provider",
    "translator_api_key": "translator_provider",
    "tts_api_key": "tts_provider",
    "tts_api_secret": "tts_provider",
    "speaker_gender_api_key": "speaker_gender_provider",
    "ocr_api_key": "ocr_provider",
}
TELEGRAM_BLACKLIST_SETTINGS = {
    "telegram_blacklisted_item_keys",
    "telegram_blacklisted_content_keys",
}
RECENT_SOURCE_SETTINGS = {
    "video_url_recent_urls",
}
TELEGRAM_STATE_SETTINGS = {
    "telegram_last_url",
    "telegram_last_post_id",
    "telegram_last_search",
    "telegram_last_filter",
    "telegram_side_panel_visible",
    "telegram_side_panel_sizes",
}
ONLINE_USER_CONFIG_SETTINGS = {
    "asr_api_base",
    "asr_fallback_to_whisper",
    "asr_language_hints",
    "asr_provider",
    "asr_timeout_seconds",
    "ocr_api_base",
    "ocr_api_region",
    "ocr_provider",
    "ocr_timeout_seconds",
    "speaker_gender_api_base",
    "speaker_gender_model",
    "speaker_gender_provider",
    "speaker_gender_timeout_seconds",
    "transcript_cleanup_api_base",
    "transcript_cleanup_model",
    "transcript_cleanup_provider",
    "transcript_cleanup_timeout_seconds",
    "translator_api_base",
    "translator_api_region",
    "translator_provider",
    "translator_timeout_seconds",
    "tts_api_base",
    "tts_api_region",
    "tts_model",
    "tts_provider",
    "tts_timeout_seconds",
}
RUNTIME_LOCAL_SETTINGS = {
    "capture_backend",
    "capture_microphone_device",
    "capture_system_device",
    "local_translation_device",
    "local_translation_model",
    "local_translation_offline",
    "ocr_model",
    "runtime_warmup_enabled",
    "runtime_warmup_translation",
    "runtime_warmup_tts",
    "runtime_warmup_whisper",
    "show_advanced_provider_options",
    "vieneu_tts_backend",
    "vieneu_tts_core",
    "vieneu_tts_device",
    "vieneu_tts_model_name",
    "vieneu_tts_offline",
    "vieneu_tts_python",
    "vieneu_tts_runtime",
    "whisper_compute_type",
    "whisper_device",
    "whisper_model",
    "whisper_offline",
}
RUNTIME_LOCAL_LEGACY_SETTINGS = RUNTIME_LOCAL_SETTINGS | ONLINE_USER_CONFIG_SETTINGS
SPLIT_SETTINGS = (
    SECRET_SETTINGS
    | set(SECRET_PAYLOAD_KEYS.values())
    | set(PROVIDER_SECRET_MAP_KEYS.values())
    | ONLINE_USER_CONFIG_SETTINGS
    | TELEGRAM_BLACKLIST_SETTINGS
    | RECENT_SOURCE_SETTINGS
    | TELEGRAM_STATE_SETTINGS
    | RUNTIME_LOCAL_SETTINGS
)


def _config_file_path(filename: str):
    return SETTINGS_FILE.parent / filename


def telegram_blacklist_file_path():
    return _config_file_path(TELEGRAM_BLACKLIST_FILENAME)


def secrets_file_path():
    return _config_file_path(SECRETS_FILENAME)


def online_user_config_file_path():
    return _config_file_path(ONLINE_USER_CONFIG_FILENAME)


def runtime_local_file_path():
    return _config_file_path(RUNTIME_LOCAL_FILENAME)


def recent_sources_file_path():
    return _config_file_path(RECENT_SOURCES_FILENAME)


def telegram_state_file_path():
    return _config_file_path(TELEGRAM_STATE_FILENAME)


def load_app_config(base: AppConfig | None = None) -> AppConfig:
    config = _with_preserved_terms_from_file(base or AppConfig.from_env())
    data = _read_settings()
    legacy_blacklist = _telegram_blacklist_from_settings(data)
    secret_values = _load_secret_settings(data)
    data.update(_read_runtime_local())
    data.update(_read_online_user_config())
    data.update(_read_recent_sources())
    data.update(_read_telegram_state())
    transient_settings = set(SESSION_ONLY_DEFAULTS) | SECRET_SETTINGS | set(SECRET_PAYLOAD_KEYS.values())
    for name in transient_settings | TELEGRAM_BLACKLIST_SETTINGS:
        data.pop(name, None)
    _migrate_removed_local_models(data)
    _migrate_removed_voice_gender_modes(data)
    _migrate_preserved_source_flags(data)
    _migrate_runtime_warmup_flags(data)
    _migrate_vieneu_v3(data)

    values: dict[str, Any] = {}
    field_map = {field.name: field for field in fields(AppConfig)}
    for name, value in data.items():
        field = field_map.get(name)
        if field is None:
            continue
        values[name] = _coerce_value(value, getattr(config, name))
    updated = _with_vieneu_v3_config(_with_preserved_terms_from_file(replace(config, **values)))
    for name, secret_value in secret_values.items():
        if not getattr(updated, name, "") and secret_value:
            updated = replace(updated, **{name: secret_value})
    updated = _migrate_online_lite_without_keys(updated)
    return _with_telegram_blacklist(updated, legacy_blacklist)


def _with_preserved_terms_from_file(config: AppConfig) -> AppConfig:
    preserved_terms = read_preserved_source_terms_file()
    return replace(config, preserved_source_terms=preserved_terms, preserved_english_terms=preserved_terms)


def _migrate_removed_local_models(data: dict[str, Any]) -> None:
    source_filter_mode = str(data.get("original_audio_voice_filter_mode") or "").strip().lower().replace("-", "_")
    if source_filter_mode in {"", "auto", "default", "fast", "center", "ffmpeg", "quick"}:
        data["original_audio_voice_filter_mode"] = "ai"

    whisper_model = str(data.get("whisper_model") or "")
    if "faster-whisper-base" in whisper_model.lower():
        data["whisper_model"] = LOCAL_WHISPER_MODEL_PATH

    provider = str(data.get("translator_provider") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if provider in {
        "auto",
        "offline_auto",
        "marian",
        "marianmt",
        "opus",
        "opus_mt",
        "opusmt",
        "argos",
        "argos_translate",
        "nllb_ct2",
        "ctranslate2",
        "ct2",
        "nllb_ctranslate2",
    }:
        data["translator_provider"] = "nllb"

    translation_model = str(data.get("local_translation_model") or "")
    if any(
        removed in translation_model.lower()
        for removed in ("models\\translation\\marian", "models/translation/marian", "distilled-600m", "ct2-int8")
    ):
        data["local_translation_model"] = LOCAL_TRANSLATION_MODEL_PATH

    cleanup_provider = str(data.get("transcript_cleanup_provider") or "").strip().lower().replace("-", "_")
    cleanup_model = str(data.get("transcript_cleanup_model") or "").strip()
    if (
        cleanup_provider
        in {
            "ollama",
            "local",
            "headless",
            "headless_local",
            "local_headless",
            "transformers",
            "llamacpp",
            "llama_cpp",
        }
        or "Qwen2.5" in cleanup_model
        or cleanup_model.lower() in {"llama3", "llama3.1"}
    ):
        data["transcript_cleanup_provider"] = "groq"
        data["transcript_cleanup_model"] = "openai/gpt-oss-20b"
        data["transcript_cleanup_api_base"] = ""
    elif cleanup_provider == "groq" and cleanup_model == "llama-3.1-8b-instant":
        data["transcript_cleanup_model"] = "openai/gpt-oss-20b"
    elif cleanup_provider in {"gemini", "google_gemini", "google_ai", "ai_studio"}:
        data["transcript_cleanup_provider"] = "groq"
        data["transcript_cleanup_model"] = "openai/gpt-oss-20b"
        data["transcript_cleanup_api_base"] = ""

    ocr_provider = str(data.get("ocr_provider") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if ocr_provider in {"hf", "huggingface", "huggingface_ocr", "huggingface_trocr", "trocr"}:
        data["ocr_provider"] = "tesseract"

    ocr_model = str(data.get("ocr_model") or "")
    normalized_ocr_model = ocr_model.lower().replace("/", "\\").rstrip("\\")
    if normalized_ocr_model.endswith("models\\ocr\\tessdata"):
        data["ocr_model"] = DEFAULT_OCR_MODEL_PATH


def _migrate_removed_voice_gender_modes(data: dict[str, Any]) -> None:
    mode = str(data.get("dubbing_auto_voice_gender_mode") or "").strip().lower().replace("-", "_")
    if mode in {"", "balanced", "default", "normal"}:
        data["dubbing_auto_voice_gender_mode"] = "ai"


def _migrate_preserved_source_flags(data: dict[str, Any]) -> None:
    if "preserve_source_terms" not in data and "preserve_english_terms" in data:
        data["preserve_source_terms"] = data["preserve_english_terms"]
    if "preserve_source_terms" in data:
        data["preserve_english_terms"] = data["preserve_source_terms"]


def _migrate_runtime_warmup_flags(data: dict[str, Any]) -> None:
    if os.getenv("AI_PLAYER_PREWARM_TTS") is not None:
        data.pop("runtime_warmup_tts", None)


def _migrate_vieneu_v3(data: dict[str, Any]) -> None:
    """One-way settings migration; no old engine can be selected afterward."""
    from ai_player.adapters.tts.tts_voices import V3_VIENEU_VOICES, migrate_vieneu_legacy_voice_id

    defaults = AppConfig()
    mode = str(data.get("vieneu_tts_mode") or "v3turbo").lower()
    model = str(data.get("vieneu_tts_model_name") or "").lower()
    legacy = mode != "v3turbo" or any(
        token in model for token in (".gguf", "/standard", "\\standard", "/turbo", "\\turbo")
    )
    legacy = legacy or str(data.get("vieneu_tts_core") or "local") != "local"
    if legacy:
        for name in ("vieneu_tts_model_name", "vieneu_tts_python", "vieneu_tts_backend"):
            data[name] = getattr(defaults, name)
    data["vieneu_tts_mode"] = "v3turbo"
    data["vieneu_tts_core"] = "local"
    data["vieneu_tts_runtime"] = "subprocess"
    data["vieneu_tts_offline"] = True
    for name in (
        "vieneu_tts_path",
        "vieneu_tts_api_base",
        "vieneu_tts_decoder_path",
        "vieneu_tts_encoder_path",
        "vieneu_tts_standard_codec_path",
    ):
        data.pop(name, None)
    if str(data.get("tts_provider") or "vieneu") == "vieneu":
        choices = tuple((voice.name, voice.id) for voice in V3_VIENEU_VOICES)
        for name in ("tts_voice", "tts_male_voice", "tts_female_voice"):
            if name in data:
                data[name] = migrate_vieneu_legacy_voice_id(data[name], choices)


def _migrate_online_lite_without_keys(config: AppConfig) -> AppConfig:
    if config.performance_preset != "online_lite":
        return config
    asr_provider = str(config.asr_provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    if asr_provider in {"assemblyai", "assembly_ai", "speechmatics"} and not str(config.asr_api_key or "").strip():
        config = replace(config, asr_provider="faster_whisper", whisper_offline=True)
    translator_provider = str(config.translator_provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    if translator_provider in {"azure_translator", "google_translate", "deepl"}:
        if not str(config.translator_api_key or "").strip():
            config = replace(
                config,
                translator_provider="nllb",
                local_translation_model=LOCAL_TRANSLATION_MODEL_PATH,
                local_translation_offline=True,
            )
    return config


def save_app_config(config: AppConfig) -> None:
    # Refuse to overwrite settings written by a newer, incompatible application.
    if SETTINGS_FILE.exists():
        try:
            payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            migrate_settings(payload)
    config = _with_vieneu_v3_config(config)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_telegram_blacklist(config.telegram_blacklisted_item_keys, config.telegram_blacklisted_content_keys)
    save_online_user_config(config)
    save_runtime_local(config)
    save_recent_sources(config.video_url_recent_urls)
    save_telegram_state(config)
    excluded_settings = set(SESSION_ONLY_DEFAULTS) | SPLIT_SETTINGS
    data = {
        field.name: getattr(config, field.name) for field in fields(AppConfig) if field.name not in excluded_settings
    }
    data["preserve_english_terms"] = bool(config.preserve_source_terms)
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    _write_json_object(SETTINGS_FILE, data)


def save_telegram_blacklist(item_keys, content_keys) -> None:
    payload = {
        "version": 1,
        "item_keys": list(_coerce_text_tuple(item_keys)),
        "content_keys": list(_coerce_text_tuple(content_keys)),
    }
    _write_json_object(telegram_blacklist_file_path(), payload)


def save_secret_settings(config: AppConfig) -> None:
    save_online_user_config(config)


def save_asr_provider_api_keys(keys: dict[str, str]) -> None:
    save_provider_api_secrets("asr_api_key", keys)


def save_provider_api_secrets(secret_name: str, keys: dict[str, str]) -> None:
    map_key = PROVIDER_SECRET_MAP_KEYS.get(secret_name)
    if not map_key:
        return
    payload = _read_json_object(online_user_config_file_path()) or {"version": 1}
    payload["version"] = 1
    protected = _protect_provider_api_secrets(secret_name, keys)
    if protected:
        payload[map_key] = protected
    else:
        payload.pop(map_key, None)
    _write_json_object(online_user_config_file_path(), payload)


def save_online_user_config(config: AppConfig) -> None:
    payload = {"version": 1}
    payload.update(_config_values(_with_vieneu_v3_config(config), ONLINE_USER_CONFIG_SETTINGS))
    payload.update(_dump_secret_settings(config))
    _write_json_object(online_user_config_file_path(), payload)


def save_runtime_local(config: AppConfig) -> None:
    payload = {"version": 1}
    payload.update(_config_values(_with_vieneu_v3_config(config), RUNTIME_LOCAL_SETTINGS))
    _write_json_object(runtime_local_file_path(), payload)


def _with_vieneu_v3_config(config: AppConfig) -> AppConfig:
    data = {field.name: getattr(config, field.name) for field in fields(AppConfig)}
    _migrate_vieneu_v3(data)
    return replace(config, **data)


def save_recent_sources(recent_urls) -> None:
    payload = {
        "version": 1,
        "video_url_recent_urls": list(_coerce_text_tuple(recent_urls)),
    }
    _write_json_object(recent_sources_file_path(), payload)


def save_telegram_state(config: AppConfig) -> None:
    payload = {"version": 1}
    payload.update(_config_values(config, TELEGRAM_STATE_SETTINGS))
    _write_json_object(telegram_state_file_path(), payload)


def _with_telegram_blacklist(config: AppConfig, legacy_blacklist: tuple[tuple[str, ...], tuple[str, ...]]) -> AppConfig:
    blacklist = _read_telegram_blacklist()
    if blacklist is None:
        blacklist = legacy_blacklist
        if blacklist[0] or blacklist[1]:
            save_telegram_blacklist(*blacklist)
    return replace(
        config,
        telegram_blacklisted_item_keys=blacklist[0],
        telegram_blacklisted_content_keys=blacklist[1],
    )


def _read_telegram_blacklist() -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    path = telegram_blacklist_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        LOGGER.info("Could not read Telegram blacklist from %s: %s", path, exc)
        return ((), ())
    if not isinstance(data, dict):
        return ((), ())
    return (
        _coerce_text_tuple(data.get("item_keys")),
        _coerce_text_tuple(data.get("content_keys")),
    )


def _telegram_blacklist_from_settings(data: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        _coerce_text_tuple(data.get("telegram_blacklisted_item_keys")),
        _coerce_text_tuple(data.get("telegram_blacklisted_content_keys")),
    )


def _read_runtime_local() -> dict[str, Any]:
    return _read_split_settings(runtime_local_file_path(), RUNTIME_LOCAL_LEGACY_SETTINGS)


def _read_online_user_config() -> dict[str, Any]:
    return _read_split_settings(online_user_config_file_path(), ONLINE_USER_CONFIG_SETTINGS)


def _read_recent_sources() -> dict[str, Any]:
    return _read_split_settings(recent_sources_file_path(), RECENT_SOURCE_SETTINGS)


def _read_telegram_state() -> dict[str, Any]:
    return _read_split_settings(telegram_state_file_path(), TELEGRAM_STATE_SETTINGS)


def _read_split_settings(path, keys: set[str]) -> dict[str, Any]:
    data = _read_json_object(path)
    if not data:
        return {}
    return {key: data[key] for key in keys if key in data}


def _read_settings() -> dict[str, Any]:
    try:
        if not SETTINGS_FILE.exists():
            return {}
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        return migrate_settings(data) if isinstance(data, dict) else {}
    except Exception as exc:
        LOGGER.info("Could not read settings from %s: %s", SETTINGS_FILE, exc)
        return {}


def _load_secret_settings(data: dict[str, Any]) -> dict[str, str]:
    online_data = _read_json_object(online_user_config_file_path())
    legacy_secret_data = _read_json_object(secrets_file_path())
    payload_sources = [source for source in (online_data, legacy_secret_data, data) if source]
    values: dict[str, str] = {}
    provider_secret_maps = {
        name: _load_provider_api_secrets_from_sources(name, payload_sources) for name in PROVIDER_SECRET_MAP_KEYS
    }
    for name, provider_keys in provider_secret_maps.items():
        if not provider_keys:
            continue
        provider = _selected_secret_provider(name, online_data, data)
        if provider in provider_keys:
            values[name] = provider_keys[provider]
    for name, payload_key in SECRET_PAYLOAD_KEYS.items():
        if name in values:
            continue
        if provider_secret_maps.get(name):
            continue
        for payload_data in payload_sources:
            try:
                value = reveal_text(payload_data.get(payload_key))
            except SecretStoreError as exc:
                LOGGER.warning("Could not reveal saved secret setting %s: %s", name, exc)
                value = ""
            if value:
                values[name] = value
                break
    return values


def _dump_secret_settings(config: AppConfig) -> dict[str, object]:
    values: dict[str, object] = {}
    for name, payload_key in SECRET_PAYLOAD_KEYS.items():
        value = str(getattr(config, name, "") or "")
        if not value:
            continue
        try:
            values[payload_key] = protect_text(value)
        except SecretStoreError as exc:
            LOGGER.warning("Could not save secret setting %s: %s", name, exc)
    for name, map_key in PROVIDER_SECRET_MAP_KEYS.items():
        provider = _secret_provider_from_config(config, name)
        secret_value = str(getattr(config, name, "") or "")
        secret_map = load_provider_api_secrets(name)
        if secret_value and provider:
            secret_map[provider] = secret_value
        protected_map = _protect_provider_api_secrets(name, secret_map)
        if protected_map:
            values[map_key] = protected_map
    return values


def load_asr_provider_api_keys() -> dict[str, str]:
    return load_provider_api_secrets("asr_api_key")


def load_provider_api_secrets(secret_name: str) -> dict[str, str]:
    if secret_name not in PROVIDER_SECRET_MAP_KEYS:
        return {}
    online_data = _read_json_object(online_user_config_file_path())
    legacy_secret_data = _read_json_object(secrets_file_path())
    settings_data = _read_settings()
    payload_sources = [source for source in (online_data, legacy_secret_data, settings_data) if source]
    keys = _load_provider_api_secrets_from_sources(secret_name, payload_sources)
    legacy_key = ""
    payload_key = SECRET_PAYLOAD_KEYS.get(secret_name, "")
    for payload_data in payload_sources:
        try:
            legacy_key = reveal_text(payload_data.get(payload_key))
        except SecretStoreError as exc:
            LOGGER.warning("Could not reveal saved secret setting %s: %s", secret_name, exc)
            legacy_key = ""
        if legacy_key:
            break
    provider = _selected_secret_provider(secret_name, online_data, settings_data)
    if legacy_key and provider and provider not in keys:
        keys[provider] = legacy_key
    return keys


def _load_asr_api_key_secrets(payload_sources: list[dict[str, Any]]) -> dict[str, str]:
    return _load_provider_api_secrets_from_sources("asr_api_key", payload_sources)


def _load_provider_api_secrets_from_sources(secret_name: str, payload_sources: list[dict[str, Any]]) -> dict[str, str]:
    map_key = PROVIDER_SECRET_MAP_KEYS.get(secret_name)
    if not map_key:
        return {}
    keys: dict[str, str] = {}
    for payload_data in payload_sources:
        raw_map = payload_data.get(map_key)
        if not isinstance(raw_map, dict):
            continue
        for provider, protected_value in raw_map.items():
            normalized = _normalize_secret_provider(secret_name, provider)
            if not normalized or normalized in keys:
                continue
            try:
                value = reveal_text(protected_value)
            except SecretStoreError as exc:
                LOGGER.warning("Could not reveal saved secret setting %s for %s: %s", secret_name, normalized, exc)
                value = ""
            if value:
                keys[normalized] = value
    return keys


def _protect_asr_provider_api_keys(values: dict[str, str]) -> dict[str, object]:
    return _protect_provider_api_secrets("asr_api_key", values)


def _protect_provider_api_secrets(secret_name: str, values: dict[str, str]) -> dict[str, object]:
    protected: dict[str, object] = {}
    for provider, key in values.items():
        normalized = _normalize_secret_provider(secret_name, provider)
        value = str(key or "")
        if not normalized or not value:
            continue
        try:
            protected[normalized] = protect_text(value)
        except SecretStoreError as exc:
            LOGGER.warning("Could not save secret setting %s for %s: %s", secret_name, normalized, exc)
    return protected


def _normalize_asr_provider(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "auto": "auto",
        "automatic": "auto",
        "assembly_ai": "assemblyai",
        "assembly": "assemblyai",
        "speech": "speechmatics",
        "speechmatic": "speechmatics",
        "whisper": "faster_whisper",
        "fasterwhisper": "faster_whisper",
    }
    return aliases.get(text, text)


def _normalize_ocr_provider(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": AppConfig().ocr_provider,
        "auto": AppConfig().ocr_provider,
        "ocrspace": "ocr_space",
        "ocr_space_api": "ocr_space",
        "azure": "azure_vision",
        "azure_read": "azure_vision",
        "azure_ocr": "azure_vision",
        "microsoft_ocr": "azure_vision",
        "google": "google_vision",
        "google_ocr": "google_vision",
        "cloud_vision": "google_vision",
        "hf": "tesseract",
        "huggingface": "tesseract",
        "huggingface_ocr": "tesseract",
        "huggingface_trocr": "tesseract",
        "trocr": "tesseract",
    }
    return aliases.get(text, text)


def _normalize_translator_provider(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": AppConfig().translator_provider,
        "none": "none",
        "off": "none",
        "passthrough": "none",
        "no_translate": "none",
        "azure": "azure_translator",
        "azure_translate": "azure_translator",
        "microsoft": "azure_translator",
        "microsoft_translator": "azure_translator",
        "google": "google_translate",
        "google_translator": "google_translate",
        "cloud_translate": "google_translate",
        "deepl": "deepl",
        "deep_l": "deepl",
        "nllb_ct2": "nllb",
        "ctranslate2": "nllb",
        "ct2": "nllb",
        "nllb_ctranslate2": "nllb",
        "local_nllb": "nllb",
        "nllb_local": "nllb",
    }
    return aliases.get(text, text)


def _normalize_tts_provider(value: object) -> str:
    compact = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "": AppConfig().tts_provider,
        "vieneu": "vieneu",
        "vieneutts": "vieneu",
        "local": "vieneu",
        "offline": "vieneu",
        "edge": "edge",
        "edgetts": "edge",
        "azure": "azure_tts",
        "azuretts": "azure_tts",
        "microsofttts": "azure_tts",
        "google": "google_tts",
        "googletts": "google_tts",
        "googlecloudtts": "google_tts",
        "gcp": "google_tts",
        "gcptts": "google_tts",
        "amazon": "amazon_polly",
        "amazonpolly": "amazon_polly",
        "polly": "amazon_polly",
        "awspolly": "amazon_polly",
        "none": "none",
        "off": "none",
        "notts": "none",
    }
    return aliases.get(compact, str(value or "").strip().lower().replace("-", "_").replace(" ", "_"))


def _normalize_cleanup_provider(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": AppConfig().transcript_cleanup_provider,
        "openai_compatible": "openai",
        "api": "openai",
        "groqcloud": "groq",
        "gemini": "groq",
        "google_gemini": "groq",
        "google_ai": "groq",
        "ai_studio": "groq",
        "open_router": "openrouter",
        "openrouter_free": "openrouter",
        "hugging_face": "huggingface",
        "hf": "huggingface",
        "hf_inference": "huggingface",
        "hf_router": "huggingface",
        "ollama": "groq",
        "local": "groq",
        "headless": "groq",
        "headless_local": "groq",
        "local_headless": "groq",
        "transformers": "groq",
        "llamacpp": "groq",
        "llama_cpp": "groq",
    }
    return aliases.get(text, text)


def _normalize_speaker_gender_provider(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": AppConfig().speaker_gender_provider,
        "default": AppConfig().speaker_gender_provider,
        "offline": "local",
        "model": "local",
        "transformers": "local",
        "hf": "huggingface_gender",
        "huggingface": "huggingface_gender",
        "huggingface_inference": "huggingface_gender",
        "huggingface_gender": "huggingface_gender",
    }
    return aliases.get(text, text)


def _normalize_secret_provider(secret_name: str, provider: object) -> str:
    if secret_name == "asr_api_key":
        return _normalize_asr_provider(provider)
    if secret_name == "ocr_api_key":
        return _normalize_ocr_provider(provider)
    if secret_name == "translator_api_key":
        return _normalize_translator_provider(provider)
    if secret_name in {"tts_api_key", "tts_api_secret"}:
        return _normalize_tts_provider(provider)
    if secret_name == "transcript_cleanup_api_key":
        return _normalize_cleanup_provider(provider)
    if secret_name == "speaker_gender_api_key":
        return _normalize_speaker_gender_provider(provider)
    return str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")


def _selected_secret_provider(
    secret_name: str,
    online_data: dict[str, Any] | None,
    settings_data: dict[str, Any] | None,
) -> str:
    provider_key = PROVIDER_SETTING_KEYS.get(secret_name)
    if not provider_key:
        return ""
    raw_provider = _payload_text(online_data, provider_key) or _payload_text(settings_data, provider_key)
    if not raw_provider:
        raw_provider = str(getattr(AppConfig(), provider_key, "") or "")
    if secret_name == "asr_api_key":
        return _selected_asr_secret_provider(raw_provider, online_data, settings_data)
    return _normalize_secret_provider(secret_name, raw_provider)


def _secret_provider_from_config(config: AppConfig, secret_name: str) -> str:
    provider_key = PROVIDER_SETTING_KEYS.get(secret_name)
    if not provider_key:
        return ""
    raw_provider = getattr(config, provider_key, "")
    if secret_name == "asr_api_key":
        return _selected_asr_secret_provider_from_config(config)
    return _normalize_secret_provider(secret_name, raw_provider)


def _selected_asr_secret_provider(
    raw_provider: object,
    online_data: dict[str, Any] | None,
    settings_data: dict[str, Any] | None,
) -> str:
    provider = _normalize_asr_provider(raw_provider)
    if provider != "auto":
        return provider
    api_base = (_payload_text(online_data, "asr_api_base") or _payload_text(settings_data, "asr_api_base")).lower()
    if "assemblyai" in api_base:
        return "assemblyai"
    if "speechmatics" in api_base:
        return "speechmatics"
    hints = _payload_text(online_data, "asr_language_hints") or _payload_text(settings_data, "asr_language_hints")
    source_language = _payload_text(settings_data, "source_language") or AppConfig().source_language
    if hints or not source_language or source_language == "auto":
        return "speechmatics"
    return "assemblyai"


def _selected_asr_secret_provider_from_config(config: AppConfig) -> str:
    provider = _normalize_asr_provider(config.asr_provider)
    if provider != "auto":
        return provider
    api_base = str(config.asr_api_base or "").strip().lower()
    if "assemblyai" in api_base:
        return "assemblyai"
    if "speechmatics" in api_base:
        return "speechmatics"
    source_language = str(config.source_language or "").strip().lower()
    if str(config.asr_language_hints or "").strip() or not source_language or source_language == "auto":
        return "speechmatics"
    return "assemblyai"


def _payload_text(data: dict[str, Any] | None, key: str) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get(key) or "").strip()


def _read_json_object(path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        LOGGER.info("Could not read JSON settings from %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_object(path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        path,
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
    )


def _config_values(config: AppConfig, keys: set[str]) -> dict[str, object]:
    return {key: getattr(config, key) for key in keys}


def _coerce_value(value: Any, current: Any) -> Any:
    if isinstance(current, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except Exception:
            return current
    if isinstance(current, float):
        try:
            number = float(value)
        except Exception:
            return current
        return number if math.isfinite(number) else current
    if isinstance(current, tuple):
        if isinstance(value, str):
            values = value.replace("\n", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            return current
        items = tuple(dict.fromkeys(item for raw in values if (item := str(raw or "").strip())))
        if current and all(isinstance(item, int) and not isinstance(item, bool) for item in current):
            coerced = []
            for item in items:
                try:
                    coerced.append(int(item))
                except (TypeError, ValueError):
                    return current
            return tuple(coerced)
        return items
    return str(value) if isinstance(current, str) else value


def _coerce_text_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return ()
    return tuple(dict.fromkeys(item for raw in values if (item := str(raw or "").strip())))
