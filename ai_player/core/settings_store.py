from __future__ import annotations

import json
from dataclasses import fields, replace
from typing import Any

from ai_player.core.config import CONFIG_DIR, AppConfig, preserved_english_terms_file_path

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

    values: dict[str, Any] = {}
    field_map = {field.name: field for field in fields(AppConfig)}
    for name, value in data.items():
        field = field_map.get(name)
        if field is None:
            continue
        values[name] = _coerce_value(value, getattr(config, name))
    return replace(config, **values)


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
