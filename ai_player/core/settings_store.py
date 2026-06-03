from __future__ import annotations

import json
import math
import os
from dataclasses import fields, replace
from typing import Any

from ai_player.core.app_logging import get_logger
from ai_player.core.config import (
    CONFIG_DIR,
    LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH,
    AppConfig,
    preserved_english_terms_file_path,
    preserved_source_terms_file_path,
    read_preserved_source_terms_file,
)
from ai_player.core.secret_store import SecretStoreError, protect_text, reveal_text

SETTINGS_FILE = CONFIG_DIR / "settings.json"
TELEGRAM_BLACKLIST_FILENAME = "telegram_blacklist.json"
SECRETS_FILENAME = "secrets.json"
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
    "transcript_cleanup_api_key",
}
SECRET_PAYLOAD_KEYS = {
    "transcript_cleanup_api_key": "transcript_cleanup_api_key_secret",
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
    "speaker_gender_model",
    "transcript_cleanup_api_base",
    "transcript_cleanup_model",
    "vieneu_tts_api_base",
    "vieneu_tts_backend",
    "vieneu_tts_core",
    "vieneu_tts_decoder_path",
    "vieneu_tts_device",
    "vieneu_tts_encoder_path",
    "vieneu_tts_model_name",
    "vieneu_tts_offline",
    "vieneu_tts_path",
    "vieneu_tts_python",
    "vieneu_tts_runtime",
    "vieneu_tts_standard_codec_path",
    "whisper_compute_type",
    "whisper_device",
    "whisper_model",
    "whisper_offline",
}
SPLIT_SETTINGS = (
    SECRET_SETTINGS
    | set(SECRET_PAYLOAD_KEYS.values())
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
    data.update(_read_recent_sources())
    data.update(_read_telegram_state())
    transient_settings = set(SESSION_ONLY_DEFAULTS) | SECRET_SETTINGS | set(SECRET_PAYLOAD_KEYS.values())
    for name in transient_settings | TELEGRAM_BLACKLIST_SETTINGS:
        data.pop(name, None)
    _migrate_removed_local_models(data)
    _migrate_preserved_source_flags(data)
    _migrate_runtime_warmup_flags(data)
    _migrate_removed_vieneu_remote(data)
    _migrate_default_vieneu_voices(data)

    values: dict[str, Any] = {}
    field_map = {field.name: field for field in fields(AppConfig)}
    for name, value in data.items():
        field = field_map.get(name)
        if field is None:
            continue
        values[name] = _coerce_value(value, getattr(config, name))
    updated = _with_preserved_terms_from_file(replace(config, **values))
    for name, secret_value in secret_values.items():
        if not getattr(updated, name, "") and secret_value:
            updated = replace(updated, **{name: secret_value})
    return _with_telegram_blacklist(updated, legacy_blacklist)


def _with_preserved_terms_from_file(config: AppConfig) -> AppConfig:
    preserved_terms = read_preserved_source_terms_file()
    return replace(config, preserved_source_terms=preserved_terms, preserved_english_terms=preserved_terms)


def _migrate_removed_local_models(data: dict[str, Any]) -> None:
    source_filter_mode = str(data.get("original_audio_voice_filter_mode") or "").strip().lower().replace("-", "_")
    if source_filter_mode in {"", "auto", "default"}:
        data["original_audio_voice_filter_mode"] = "fast"

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
    }:
        data["translator_provider"] = "nllb_ct2"

    translation_model = str(data.get("local_translation_model") or "")
    if "models\\translation\\marian" in translation_model or "models/translation/marian" in translation_model:
        data["local_translation_model"] = LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH

    cleanup_model = str(data.get("transcript_cleanup_model") or "")
    if "Qwen2.5-7B-Instruct" in cleanup_model and not LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists():
        data["transcript_cleanup_model"] = "llama3.1"
    elif "Qwen2.5-7B-Instruct" in cleanup_model:
        data["transcript_cleanup_model"] = str(LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH)


def _migrate_preserved_source_flags(data: dict[str, Any]) -> None:
    if "preserve_source_terms" not in data and "preserve_english_terms" in data:
        data["preserve_source_terms"] = data["preserve_english_terms"]
    if "preserve_source_terms" in data:
        data["preserve_english_terms"] = data["preserve_source_terms"]


def _migrate_runtime_warmup_flags(data: dict[str, Any]) -> None:
    if os.getenv("AI_PLAYER_PREWARM_TTS") is not None:
        data.pop("runtime_warmup_tts", None)


def _migrate_removed_vieneu_remote(data: dict[str, Any]) -> None:
    core = str(data.get("vieneu_tts_core") or "").strip().lower().replace("-", "_").replace(" ", "_")
    mode = str(data.get("vieneu_tts_mode") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if core not in {"remote", "remote_api", "api", "remoteapi"} and mode not in {"remote", "remote_api", "api"}:
        return

    defaults = AppConfig()
    data["vieneu_tts_core"] = "local"
    data["vieneu_tts_mode"] = "turbo"
    data["vieneu_tts_api_base"] = ""
    data["vieneu_tts_model_name"] = defaults.vieneu_tts_model_name
    data["vieneu_tts_path"] = defaults.vieneu_tts_path
    data["vieneu_tts_python"] = defaults.vieneu_tts_python
    data["vieneu_tts_decoder_path"] = defaults.vieneu_tts_decoder_path
    data["vieneu_tts_encoder_path"] = defaults.vieneu_tts_encoder_path
    data["vieneu_tts_standard_codec_path"] = defaults.vieneu_tts_standard_codec_path
    data["vieneu_tts_offline"] = True


def _migrate_default_vieneu_voices(data: dict[str, Any]) -> None:
    if str(data.get("tts_provider") or "vieneu").strip().lower() not in {"", "vieneu"}:
        return
    replacements = {
        "tts_voice": ({"Bích Ngọc", "Bich Ngoc"}, "Thục Đoan"),
        "tts_female_voice": ({"Bích Ngọc", "Bich Ngoc"}, "Thục Đoan"),
        "tts_male_voice": ({"Phạm Tuyên", "Pham Tuyen"}, "Xuân Vĩnh"),
    }
    for key, (old_voices, new_voice) in replacements.items():
        if str(data.get(key) or "") in old_voices:
            data[key] = new_voice


def save_app_config(config: AppConfig) -> None:
    config = _without_removed_vieneu_remote_config(config)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_telegram_blacklist(config.telegram_blacklisted_item_keys, config.telegram_blacklisted_content_keys)
    save_secret_settings(config)
    save_runtime_local(config)
    save_recent_sources(config.video_url_recent_urls)
    save_telegram_state(config)
    excluded_settings = set(SESSION_ONLY_DEFAULTS) | SPLIT_SETTINGS
    data = {
        field.name: getattr(config, field.name)
        for field in fields(AppConfig)
        if field.name not in excluded_settings
    }
    data["preserve_english_terms"] = bool(config.preserve_source_terms)
    _write_json_object(SETTINGS_FILE, data)


def save_telegram_blacklist(item_keys, content_keys) -> None:
    payload = {
        "version": 1,
        "item_keys": list(_coerce_text_tuple(item_keys)),
        "content_keys": list(_coerce_text_tuple(content_keys)),
    }
    _write_json_object(telegram_blacklist_file_path(), payload)


def save_secret_settings(config: AppConfig) -> None:
    payload = {"version": 1}
    payload.update(_dump_secret_settings(config))
    _write_json_object(secrets_file_path(), payload)


def save_runtime_local(config: AppConfig) -> None:
    payload = {"version": 1}
    payload.update(_config_values(_without_removed_vieneu_remote_config(config), RUNTIME_LOCAL_SETTINGS))
    _write_json_object(runtime_local_file_path(), payload)


def _without_removed_vieneu_remote_config(config: AppConfig) -> AppConfig:
    core = str(config.vieneu_tts_core or "").strip().lower().replace("-", "_").replace(" ", "_")
    mode = str(config.vieneu_tts_mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    if core not in {"remote", "remote_api", "api", "remoteapi"} and mode not in {"remote", "remote_api", "api"}:
        return replace(config, vieneu_tts_core="local", vieneu_tts_api_base="")
    defaults = AppConfig()
    return replace(
        config,
        vieneu_tts_core="local",
        vieneu_tts_mode="turbo",
        vieneu_tts_api_base="",
        vieneu_tts_model_name=defaults.vieneu_tts_model_name,
        vieneu_tts_path=defaults.vieneu_tts_path,
        vieneu_tts_python=defaults.vieneu_tts_python,
        vieneu_tts_decoder_path=defaults.vieneu_tts_decoder_path,
        vieneu_tts_encoder_path=defaults.vieneu_tts_encoder_path,
        vieneu_tts_standard_codec_path=defaults.vieneu_tts_standard_codec_path,
        vieneu_tts_offline=True,
    )


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
    return _read_split_settings(runtime_local_file_path(), RUNTIME_LOCAL_SETTINGS)


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
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        LOGGER.info("Could not read settings from %s: %s", SETTINGS_FILE, exc)
        return {}


def _load_secret_settings(data: dict[str, Any]) -> dict[str, str]:
    secret_data = _read_json_object(secrets_file_path())
    payload_data = data if secret_data is None else secret_data
    values: dict[str, str] = {}
    for name, payload_key in SECRET_PAYLOAD_KEYS.items():
        try:
            values[name] = reveal_text(payload_data.get(payload_key))
        except SecretStoreError as exc:
            LOGGER.warning("Could not reveal saved secret setting %s: %s", name, exc)
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
    return values


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
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
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
