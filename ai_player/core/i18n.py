from __future__ import annotations

from functools import lru_cache

from ai_player.core.runtime_catalog import load_gui_translations


@lru_cache(maxsize=1)
def _gui_translations() -> dict[str, dict[str, str]]:
    return load_gui_translations()


def ui_text(key: str, language_id: str | None = None, **kwargs: object) -> str:
    translations = _gui_translations()
    fallback = translations.get("vi", {})
    language = str(language_id or "vi").strip() or "vi"
    text = translations.get(language, fallback).get(key, fallback.get(key, key))
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except Exception:
        return text
