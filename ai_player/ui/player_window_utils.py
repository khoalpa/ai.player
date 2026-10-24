from __future__ import annotations

import html
import math
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from ai_player.configuration import AppConfig
from ai_player.core.value_utils import optional_float
from ai_player.runtime.gpu import ctranslate2_cuda_available, torch_cuda_available
from ai_player.runtime.runtime_catalog import (
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
    return optional_float(value)


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
            num = float(numerator)
            if den == 0 or not math.isfinite(den) or not math.isfinite(num):
                return unknown
            return f"{num / den:.2f}"
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
    cuda_disabled = os.getenv("AI_PLAYER_DISABLE_CUDA", "").strip().lower() in {"1", "true", "yes", "on"}
    changes: dict[str, object] = {}

    whisper_device = _device_value(config.whisper_device)
    if whisper_device != "cpu" and (cuda_disabled or not ctranslate2_cuda_available()):
        changes.update(whisper_device="cpu", whisper_compute_type="int8")

    translation_device = _device_value(config.local_translation_device)
    if translation_device != "cpu" and (cuda_disabled or not _translation_cuda_ready(config)):
        changes["local_translation_device"] = "cpu"

    vieneu_device = _device_value(config.vieneu_tts_device)
    if vieneu_device != "cpu" and (cuda_disabled or not _vieneu_cuda_ready()):
        changes.update(vieneu_tts_device="cpu", vieneu_tts_backend="native")

    return replace(config, **changes) if changes else config


def _device_value(value: object) -> str:
    device = str(value or "auto").strip().lower()
    return device if device in {"auto", "cpu", "cuda"} else "auto"


def _translation_cuda_ready(config: AppConfig) -> bool:
    provider = str(config.translator_provider or "nllb").strip().lower().replace("-", "_")
    model = str(config.local_translation_model or "").strip().lower()
    if provider in {"none", "off", "passthrough"}:
        return True
    if provider in {"nllb_ct2", "ctranslate2", "ct2", "nllb_ctranslate2"} or "ct2" in model:
        return ctranslate2_cuda_available()
    return torch_cuda_available()


def _vieneu_cuda_ready() -> bool:
    # VieNeu currently resolves its runtime device through PyTorch. ONNX CUDA
    # remains useful for its decoder, but is not sufficient to run the model.
    return torch_cuda_available()
