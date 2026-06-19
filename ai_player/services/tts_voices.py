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

ELEVENLABS_TTS_VOICES = [
    VoiceOption("21m00Tcm4TlvDq8ikWAM", "ElevenLabs Rachel (female)"),
    VoiceOption("JBFqnCBsd6RMkjVDRZzb", "ElevenLabs George (male)"),
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
        VoiceOption("azure_tts", "Azure TTS"),
        VoiceOption("google_tts", "Google Cloud TTS"),
        VoiceOption("amazon_polly", "Amazon Polly"),
        VoiceOption("elevenlabs_tts", "ElevenLabs TTS"),
    ]


def available_vieneu_mode_options() -> list[VoiceOption]:
    return [
        VoiceOption("turbo", "Turbo"),
        VoiceOption("standard", "Standard"),
    ]


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
    if provider_key == "elevenlabs_tts":
        if normalized in {"jbfqncbsd6rmkjvdrzzb", "george"}:
            return "male"
        if normalized in {"21m00tcm4tlvdq8ikwam", "rachel"}:
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
    if raw in {"azure", "azuretts", "microsofttts", "microsoftazuretts"}:
        return "azure_tts"
    if raw in {"google", "googletts", "googlecloudtts", "gcp", "gcptts"}:
        return "google_tts"
    if raw in {"amazon", "amazonpolly", "polly", "awspolly"}:
        return "amazon_polly"
    if raw in {"elevenlabs", "elevenlabstts", "eleven", "elevenlabsapi"}:
        return "elevenlabs_tts"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"
