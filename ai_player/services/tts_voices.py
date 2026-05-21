from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path


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

STANDARD_VIENEU_VOICES = [
    VoiceOption("Binh", "Bình (nam miền Bắc)"),
    VoiceOption("Tuyen", "Tuyên (nam miền Bắc)"),
    VoiceOption("Ngoc", "Ngọc (nữ miền Bắc)"),
    VoiceOption("Ly", "Ly (nữ miền Bắc)"),
    VoiceOption("Vinh", "Vĩnh (nam miền Nam)"),
    VoiceOption("Doan", "Đoan (nữ miền Nam)"),
]

TURBO_VIENEU_VOICES = [
    VoiceOption("Bích Ngọc", "Bích Ngọc (nữ miền Bắc)"),
    VoiceOption("Phạm Tuyên", "Phạm Tuyên (nam miền Bắc)"),
    VoiceOption("Thục Đoan", "Thục Đoan (nữ miền Nam)"),
    VoiceOption("Xuân Vĩnh", "Xuân Vĩnh (nam miền Nam)"),
]


def available_tts_provider_options() -> list[VoiceOption]:
    return [
        VoiceOption("none", "Không TTS"),
        VoiceOption("vieneu", "VieNeu-TTS"),
        VoiceOption("edge", "Edge TTS"),
    ]


def available_vieneu_mode_options() -> list[VoiceOption]:
    return [
        VoiceOption("turbo", "Turbo"),
        VoiceOption("standard", "Standard"),
    ]


def voice_gender(provider: str, voice_id: object) -> str:
    normalized = normalize_voice_token(voice_id)
    if _voice_provider_key(provider) == "edge":
        if "namminh" in normalized or "nam minh" in normalized:
            return "male"
        if "hoai my" in normalized or "hoaimy" in normalized:
            return "female"

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

    hints = {
        "binh": ("binh", "nam", "bac"),
        "tuyen": ("tuyen", "nam", "bac"),
        "ngoc": ("ngoc", "nu", "bac"),
        "ly": ("ly", "nu", "bac"),
        "vinh": ("vinh", "nam", "nam"),
        "doan": ("doan", "nu", "nam"),
    }.get(normalized)
    if not hints:
        return raw

    ranked: list[tuple[int, str]] = []
    for clean_id, norm_id, norm_label in entries:
        haystack = f"{norm_id} {norm_label}"
        score = sum(1 for hint in hints if hint in haystack)
        if score:
            ranked.append((score, clean_id))
    if ranked:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][1]
    return raw


def vieneu_model_voices_path(model_name: str) -> Path:
    model_path = Path(str(model_name or ""))
    if model_path.exists() and model_path.is_dir():
        return model_path / "voices.json"
    if model_path.exists() and model_path.is_file():
        return model_path.parent / "voices.json"
    return Path()


def read_vieneu_voices(voices_path: Path) -> list[VoiceOption]:
    try:
        data = json.loads(voices_path.read_text(encoding="utf-8-sig"))
        presets = data.get("presets", {})
        return [
            VoiceOption(str(voice_id), str(preset.get("description") or voice_id))
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
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"
