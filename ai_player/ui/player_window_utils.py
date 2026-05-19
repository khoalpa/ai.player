from __future__ import annotations

import html
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.core.runtime_catalog import (
    available_dropdown_options,
    load_gui_text_aliases,
    load_gui_translations,
    load_performance_presets,
)

UI_TEXT = load_gui_translations()
UI_TEXT_ALIASES = load_gui_text_aliases()
PERFORMANCE_PRESETS = load_performance_presets()


def repair_mojibake(text: str) -> str:
    value = str(text or "")
    mojibake_markers = (
        "\u00c3",
        "\u00e1\u00ba",
        "\u00e1\u00bb",
        "\u00c4",
        "\u00c6",
        "\u00c2",
        "\u00d0",
        "\u00f0",
        "\u00bb",
        "\u00bf",
    )
    if not any(marker in value for marker in mojibake_markers):
        return value
    try:
        repaired = value.encode("cp1252").decode("utf-8")
    except Exception:
        return value
    return repaired if repaired else value


def ui_label(text: str) -> str:
    return repair_mojibake(text)


def html_with_breaks(text: str) -> str:
    return html.escape(str(text or "")).replace("\n", "<br>")


def dropdown_options(folder_name: str, language_id: str | None = None) -> list[tuple[str, str]]:
    return [(option.label, option.value) for option in available_dropdown_options(folder_name, language_id=language_id)]


def float_value(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def format_bitrate(value, unknown: str = "không rõ") -> str:
    bitrate = float_value(value)
    if bitrate is None or bitrate <= 0:
        return unknown
    if bitrate >= 1_000_000:
        return f"{bitrate / 1_000_000:.2f} Mbps"
    return f"{bitrate / 1_000:.0f} kbps"


def format_rate(value, unknown: str = "không rõ") -> str:
    text = str(value or "").strip()
    if not text or text == "0/0":
        return unknown
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            den = float(denominator)
            if den == 0:
                return unknown
            return f"{float(numerator) / den:.2f}"
        except Exception:
            return text
    return text


def is_ytdlp_source_cache(path: Path) -> bool:
    try:
        path.relative_to(Path(tempfile.gettempdir()) / "ai-player-sources")
        return True
    except ValueError:
        return False


def safe_native_dubbing_config(config: AppConfig) -> AppConfig:
    if os.getenv("AI_PLAYER_ENABLE_CUDA", "").strip().lower() in {"1", "true", "yes", "on"}:
        return config
    if not any(
        str(value or "").strip().lower() == "cuda"
        for value in (
            config.local_translation_device,
            config.whisper_device,
            config.vieneu_tts_device,
        )
    ):
        return config
    return replace(
        config,
        local_translation_device="cpu",
        whisper_device="cpu",
        whisper_compute_type="int8",
        vieneu_tts_device="cpu",
        vieneu_tts_backend="native",
    )
