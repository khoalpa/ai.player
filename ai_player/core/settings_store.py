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


def load_app_config(base: AppConfig | None = None) -> AppConfig:
    config = _with_preserved_terms_from_file(base or AppConfig.from_env())
    data = _read_settings()
    if not data:
        return config
    secret_values = _load_secret_settings(data)
    for name in set(SESSION_ONLY_DEFAULTS) | SECRET_SETTINGS:
        data.pop(name, None)
    for name in SECRET_PAYLOAD_KEYS.values():
        data.pop(name, None)
    _migrate_removed_local_models(data)
    _migrate_preserved_source_flags(data)
    _migrate_runtime_warmup_flags(data)
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
    return updated


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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {field.name: getattr(config, field.name) for field in fields(AppConfig) if field.name not in SECRET_SETTINGS}
    data.update(SESSION_ONLY_DEFAULTS)
    data.update(_dump_secret_settings(config))
    data["preserve_english_terms"] = bool(config.preserve_source_terms)
    data["preserved_source_terms_file"] = str(preserved_source_terms_file_path())
    data["preserved_english_terms_file"] = str(preserved_english_terms_file_path())
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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
    values: dict[str, str] = {}
    for name, payload_key in SECRET_PAYLOAD_KEYS.items():
        try:
            values[name] = reveal_text(data.get(payload_key))
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
    return str(value) if isinstance(current, str) else value
