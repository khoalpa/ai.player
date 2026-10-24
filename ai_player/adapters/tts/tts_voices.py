from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ai_player.configuration import RESOURCE_ROOT


@dataclass(frozen=True)
class VoiceOption:
    id: str
    name: str


@dataclass(frozen=True)
class VieNeuModelOption:
    id: str
    name: str
    offline: bool


EDGE_VOICES = [
    VoiceOption("vi-VN-HoaiMyNeural", "Hoài My (nữ, Việt Nam)"),
    VoiceOption("vi-VN-NamMinhNeural", "Nam Minh (nam, Việt Nam)"),
]

AZURE_TTS_VOICES = [
    VoiceOption("vi-VN-HoaiMyNeural", "Azure Hoai My (female, vi-VN)"),
    VoiceOption("vi-VN-NamMinhNeural", "Azure Nam Minh (male, vi-VN)"),
]

GOOGLE_TTS_VOICES = [
    VoiceOption("vi-VN-Neural2-A", "Google Neural2 A (female, vi-VN)"),
    VoiceOption("vi-VN-Neural2-D", "Google Neural2 D (male, vi-VN)"),
    VoiceOption("vi-VN-Wavenet-A", "Google Wavenet A (female, vi-VN)"),
    VoiceOption("vi-VN-Wavenet-B", "Google Wavenet B (male, vi-VN)"),
    VoiceOption("vi-VN-Wavenet-C", "Google Wavenet C (female, vi-VN)"),
    VoiceOption("vi-VN-Wavenet-D", "Google Wavenet D (male, vi-VN)"),
    VoiceOption("vi-VN-Standard-A", "Google Standard A (female, vi-VN)"),
    VoiceOption("vi-VN-Standard-B", "Google Standard B (male, vi-VN)"),
    VoiceOption("vi-VN-Standard-C", "Google Standard C (female, vi-VN)"),
    VoiceOption("vi-VN-Standard-D", "Google Standard D (male, vi-VN)"),
]

AMAZON_POLLY_VOICES = [
    VoiceOption("Joanna", "Amazon Polly Joanna (female, en-US)"),
    VoiceOption("Matthew", "Amazon Polly Matthew (male, en-US)"),
    VoiceOption("Ruth", "Amazon Polly Ruth (female, en-US)"),
    VoiceOption("Stephen", "Amazon Polly Stephen (male, en-US)"),
]

_V3_CATALOG = json.loads((RESOURCE_ROOT / "tts" / "voices_v3_turbo.json").read_text(encoding="utf-8"))["presets"]
V3_VIENEU_VOICES = [
    VoiceOption(name, f"{name} — {entry.get('description', '')}") for name, entry in _V3_CATALOG.items()
]


def available_tts_provider_options(*, include_advanced: bool = False) -> list[VoiceOption]:
    providers = [
        VoiceOption("none", "Không TTS"),
        VoiceOption("vieneu", "VieNeu-TTS"),
        VoiceOption("edge", "Edge TTS"),
    ]
    if not include_advanced:
        return providers
    return [
        *providers,
        VoiceOption("azure_tts", "Azure TTS"),
        VoiceOption("google_tts", "Google Cloud TTS"),
        VoiceOption("amazon_polly", "Amazon Polly"),
    ]


def available_vieneu_mode_options() -> list[VoiceOption]:
    return [VoiceOption("v3turbo", "VieNeu-TTS v3 Turbo")]


def voice_gender(provider: str, voice_id: object) -> str:
    normalized = normalize_voice_token(voice_id)
    provider_key = _voice_provider_key(provider)
    if provider_key in {"edge", "azure_tts"}:
        if "namminh" in normalized or "nam minh" in normalized:
            return "male"
        if "hoai my" in normalized or "hoaimy" in normalized:
            return "female"
    if provider_key == "google_tts":
        if any(
            token in normalized
            for token in (
                "neural2 d",
                "neural2-d",
                "wavenet b",
                "wavenet-b",
                "wavenet d",
                "wavenet-d",
                "standard b",
                "standard-b",
                "standard d",
                "standard-d",
            )
        ):
            return "male"
        if any(
            token in normalized
            for token in (
                "neural2 a",
                "neural2-a",
                "wavenet a",
                "wavenet-a",
                "wavenet c",
                "wavenet-c",
                "standard a",
                "standard-a",
                "standard c",
                "standard-c",
            )
        ):
            return "female"
    if provider_key == "amazon_polly":
        if normalized in {"matthew", "stephen"}:
            return "male"
        if normalized in {"joanna", "ruth"}:
            return "female"
    for name, entry in _V3_CATALOG.items():
        if normalized == normalize_voice_token(name):
            return entry.get("gender", "unknown")
    female_tokens = {
        "doan",
        "thuc doan",
        "ngoc",
        "bich ngoc",
        "ly",
        "hoai my",
        "hoaimy",
    }
    male_tokens = {
        "binh",
        "tuyen",
        "pham tuyen",
        "vinh",
        "xuan vinh",
        "nam minh",
        "namminh",
    }
    if normalized in female_tokens or any(token in normalized for token in female_tokens):
        return "female"
    if normalized in male_tokens or any(token in normalized for token in male_tokens):
        return "male"
    return "unknown"


def migrate_vieneu_legacy_voice_id(
    voice_id: object,
    available_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    raw = str(voice_id or "").strip()
    normalized = normalize_voice_token(raw)
    if not normalized:
        return raw

    entries = []
    for label, preset_id in tuple(available_choices or ()):
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if clean_id:
            entries.append((clean_id, normalize_voice_token(clean_id), normalize_voice_token(clean_label)))

    for clean_id, norm_id, norm_label in entries:
        if normalized in {norm_id, norm_label, normalize_voice_token(norm_label.split("(", 1)[0])}:
            return clean_id

    renamed = {
        "binh": "Thanh Bình",
        "tuyen": "Phạm Tuyên",
        "ngoc": "Ngọc Linh",
        "ly": "Trúc Ly",
        "vinh": "Xuân Vĩnh",
        "doan": "Thục Đoan",
        "bich ngoc": "Ngọc Linh",
    }
    return renamed.get(normalized, raw)


def vieneu_model_voices_path(model_name: str) -> Path:
    model_path = Path(str(model_name or ""))
    if model_path.exists() and model_path.is_dir():
        return model_path / "model" / "voices_v3_turbo.json"
    if model_path.exists() and model_path.is_file():
        return model_path.parent / "voices_v3_turbo.json"
    return Path()


def read_vieneu_voices(voices_path: Path) -> list[VoiceOption]:
    try:
        data = json.loads(voices_path.read_text(encoding="utf-8-sig"))
        presets = data.get("presets", {})
        return [
            VoiceOption(str(voice_id), f"{voice_id} — {preset.get('description', '')}")
            for voice_id, preset in presets.items()
            if isinstance(preset, dict)
        ]
    except Exception:
        return []


def normalize_voice_token(value: object) -> str:
    text = _strip_accents(value).replace("đ", "d").replace("Đ", "D")
    return " ".join(text.strip().lower().split())


def _strip_accents(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _voice_provider_key(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if raw in {"edge", "edgetts", "edgecli"}:
        return "edge"
    if raw in {"azure", "azuretts", "microsofttts", "microsoftazuretts"}:
        return "azure_tts"
    if raw in {"google", "googletts", "googlecloudtts", "gcp", "gcptts"}:
        return "google_tts"
    if raw in {"amazon", "amazonpolly", "polly", "awspolly"}:
        return "amazon_polly"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"
