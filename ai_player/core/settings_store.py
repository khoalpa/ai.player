from __future__ import annotations

import json
from dataclasses import fields, replace
from typing import Any

from ai_player.core.config import (
    CONFIG_DIR,
    LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH,
    AppConfig,
    preserved_english_terms_file_path,
)

SETTINGS_FILE = CONFIG_DIR / "settings.json"
SESSION_ONLY_DEFAULTS = {
    "audio_source": "original",
    "transcript_path": "",
    "dubbing_enabled_by_default": False,
    "preserved_english_terms_file": str(preserved_english_terms_file_path()),
}
SECRET_SETTINGS = {
    "transcript_cleanup_api_key",
}


def load_app_config(base: AppConfig | None = None) -> AppConfig:
    config = base or AppConfig.from_env()
    data = _read_settings()
    if not data:
        return config
    for name in set(SESSION_ONLY_DEFAULTS) | SECRET_SETTINGS:
        data.pop(name, None)
    _migrate_removed_local_models(data)

    values: dict[str, Any] = {}
    field_map = {field.name: field for field in fields(AppConfig)}
    for name, value in data.items():
        field = field_map.get(name)
        if field is None:
            continue
        values[name] = _coerce_value(value, getattr(config, name))
    return replace(config, **values)


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


def save_app_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {field.name: getattr(config, field.name) for field in fields(AppConfig) if field.name not in SECRET_SETTINGS}
    data.update(SESSION_ONLY_DEFAULTS)
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
    except Exception:
        return {}


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
            return float(value)
        except Exception:
            return current
    return str(value) if isinstance(current, str) else value
