from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import (
    CONFIG_DIR,
    OCR_MODELS_PATH,
    PROJECT_ROOT,
    TRANSCRIPT_CLEANUP_MODELS_PATH,
    TRANSLATION_MODELS_PATH,
)


@dataclass(frozen=True)
class RuntimeOption:
    id: str
    name: str


@dataclass(frozen=True)
class DropdownOption:
    label: str
    value: str


LANGUAGE_NAMES = {
    "auto": "Tự động",
    "ar": "Tiếng Ả Rập",
    "de": "Tiếng Đức",
    "en": "Tiếng Anh",
    "es": "Tiếng Tây Ban Nha",
    "fr": "Tiếng Pháp",
    "hi": "Tiếng Hindi",
    "id": "Tiếng Indonesia",
    "it": "Tiếng Ý",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "pt": "Tiếng Bồ Đào Nha",
    "ru": "Tiếng Nga",
    "th": "Tiếng Thái",
    "tr": "Tiếng Thổ Nhĩ Kỳ",
    "vi": "Tiếng Việt",
    "zh": "Tiếng Trung",
}

TESSDATA_TO_LANGUAGE = {
    "ara": "ar",
    "chi_sim": "zh",
    "deu": "de",
    "eng": "en",
    "fra": "fr",
    "hin": "hi",
    "ind": "id",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "por": "pt",
    "rus": "ru",
    "spa": "es",
    "tha": "th",
    "tur": "tr",
    "vie": "vi",
}

DEFAULT_SOURCE_LANGUAGE_CODES = (
    "auto",
    "en",
    "ja",
    "zh",
    "ko",
    "fr",
    "de",
    "es",
    "ru",
    "th",
    "id",
    "vi",
)
DEFAULT_TARGET_LANGUAGE_CODES = tuple(code for code in DEFAULT_SOURCE_LANGUAGE_CODES if code != "auto")
LANGUAGE_PACKS_DIR = PROJECT_ROOT / "ai_player" / "resources" / "languages"
LANGUAGE_PACK_FALLBACKS = ("vi", "en", "vietnamese", "english")
PRESET_PATH_SETTING_KEYS = {
    "local_translation_model",
    "transcript_cleanup_model",
    "tts_voice",
    "vieneu_tts_decoder_path",
    "vieneu_tts_encoder_path",
    "vieneu_tts_model_name",
    "vieneu_tts_standard_codec_path",
    "whisper_model",
}


def available_language_options(*, include_auto: bool, language_id: str | None = None) -> list[RuntimeOption]:
    folder = "source_languages" if include_auto else "target_languages"
    configured = available_dropdown_options(folder, language_id=language_id)
    if configured:
        return [RuntimeOption(option.value, option.label) for option in configured]

    codes = set(DEFAULT_SOURCE_LANGUAGE_CODES if include_auto else DEFAULT_TARGET_LANGUAGE_CODES)
    if not include_auto:
        codes.discard("auto")
    codes.update(_scan_tessdata_languages())
    codes.update(_scan_marian_languages(include_auto=include_auto))
    ordered = (("auto",) if include_auto else ()) + tuple(code for code in LANGUAGE_NAMES if code != "auto")
    options = [RuntimeOption(code, LANGUAGE_NAMES.get(code, code)) for code in ordered if code in codes]
    extra = sorted(code for code in codes if code not in {option.id for option in options})
    options.extend(RuntimeOption(code, code) for code in extra)
    return options


def available_dropdown_options(
    folder_name: str,
    defaults: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    language_id: str | None = None,
) -> list[DropdownOption]:
    options = _language_pack_dropdown_options(folder_name, language_id)
    if options:
        return _unique_dropdown_options(options)

    folder = PROJECT_ROOT / "ai_player" / "resources" / folder_name
    options: list[DropdownOption] = []
    if folder.exists():
        for path in sorted(folder.iterdir(), key=lambda item: item.stem.lower()):
            if not path.is_file():
                continue
            option = _read_dropdown_option_file(path)
            if option is not None:
                options.append(option)
    if not options:
        options = [DropdownOption(str(label), str(value)) for label, value in defaults]
    return _unique_dropdown_options(options)


def _language_pack_dropdown_options(folder_name: str, language_id: str | None = None) -> list[DropdownOption]:
    for pack_dir in _preferred_language_pack_dirs(language_id):
        path = pack_dir / f"{folder_name}.json"
        if not path.is_file():
            continue
        options = _read_dropdown_options_file(path)
        if options:
            return options
    return []


def _read_dropdown_options_file(path: Path) -> list[DropdownOption]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    raw_options = data.get("options", data) if isinstance(data, dict) else data
    if not isinstance(raw_options, list):
        return []
    options: list[DropdownOption] = []
    for index, item in enumerate(raw_options):
        option = _dropdown_option_from_data(item, fallback_value=str(index))
        if option is not None:
            options.append(option)
    return options


def _read_dropdown_option_file(path: Path) -> DropdownOption | None:
    value = path.stem.strip()
    label = value
    if not value:
        return None
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            value = str(data.get("value") or data.get("id") or data.get("code") or value).strip() or value
            label = str(data.get("label") or data.get("name") or label).strip() or label
    else:
        try:
            first_line = path.read_text(encoding="utf-8-sig").splitlines()[0].strip()
            if first_line:
                label = first_line
        except Exception:
            pass
    return DropdownOption(label, value)


def _dropdown_option_from_data(data, fallback_value: str) -> DropdownOption | None:
    value = fallback_value.strip()
    label = value
    if isinstance(data, dict):
        value = str(data.get("value") or data.get("id") or data.get("code") or value).strip() or value
        label = str(data.get("label") or data.get("name") or label).strip() or label
    elif data is not None:
        value = str(data).strip()
        label = value
    if not value:
        return None
    return DropdownOption(label, value)


def _unique_dropdown_options(options: list[DropdownOption]) -> list[DropdownOption]:
    unique: list[DropdownOption] = []
    seen: set[str] = set()
    for option in options:
        if option.value in seen:
            continue
        seen.add(option.value)
        unique.append(option)
    return unique


def available_gui_language_options() -> list[RuntimeOption]:
    options: list[RuntimeOption] = []
    if LANGUAGE_PACKS_DIR.exists():
        for path in sorted(LANGUAGE_PACKS_DIR.iterdir(), key=lambda item: item.stem.lower()):
            if path.is_dir():
                option = _read_gui_language_pack(path)
                if option is not None:
                    options.append(option)
                continue
            if not _is_gui_language_file(path):
                continue
            option = _read_gui_language_file(path)
            if option is not None:
                options.append(option)
    if not options:
        options = [RuntimeOption("vi", "Tiếng Việt"), RuntimeOption("en", "English")]
    return _unique_options(options)


def load_gui_translations() -> dict[str, dict[str, str]]:
    translations: dict[str, dict[str, str]] = {}
    if LANGUAGE_PACKS_DIR.exists():
        for pack_dir in sorted(
            (path for path in LANGUAGE_PACKS_DIR.iterdir() if path.is_dir()), key=lambda item: item.name.lower()
        ):
            data = _read_language_pack_data(pack_dir)
            if not isinstance(data, dict):
                continue
            language_id = str(data.get("id") or data.get("code") or pack_dir.name).strip() or pack_dir.name
            strings = data.get("strings", {})
            if isinstance(strings, dict):
                translations[language_id] = {str(key): str(value) for key, value in strings.items()}

        for path in sorted(LANGUAGE_PACKS_DIR.glob("*.json"), key=lambda item: item.stem.lower()):
            if not _is_gui_language_file(path):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            language_id = str(data.get("id") or data.get("code") or path.stem).strip() or path.stem
            strings = data.get("strings", {})
            if isinstance(strings, dict):
                translations[language_id] = {str(key): str(value) for key, value in strings.items()}
    if "vi" not in translations:
        translations["vi"] = {}
    return translations


def load_gui_text_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for aliases_path in (
        LANGUAGE_PACKS_DIR / "aliases.json",
        *(pack / "aliases.json" for pack in _language_pack_dirs()),
    ):
        try:
            data = json.loads(aliases_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        raw_aliases = data.get("aliases", data)
        if not isinstance(raw_aliases, dict):
            continue
        aliases.update({str(key): str(value) for key, value in raw_aliases.items()})
    return aliases


def _is_gui_language_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    if path.stem.lower() in {"aliases", "_aliases", "metadata", "_metadata"}:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("strings"), dict)


def load_performance_presets() -> dict[str, dict[str, object]]:
    presets: dict[str, dict[str, object]] = {}
    preset_options_path = _language_pack_dropdown_file("performance_presets", _configured_gui_language())
    if preset_options_path is not None:
        try:
            data = json.loads(preset_options_path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        raw_options = data.get("options", data) if isinstance(data, dict) else data
        if isinstance(raw_options, list):
            for item in raw_options:
                if not isinstance(item, dict):
                    continue
                preset_id = str(item.get("value") or item.get("id") or item.get("code") or "").strip()
                settings = item.get("settings", {})
                if preset_id and isinstance(settings, dict):
                    presets[preset_id] = _resolve_preset_settings(settings)
        if presets:
            return presets

    presets_dir = PROJECT_ROOT / "ai_player" / "resources" / "performance_presets"
    if not presets_dir.exists():
        return presets
    for path in sorted(presets_dir.glob("*.json"), key=lambda item: item.stem.lower()):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        preset_id = str(data.get("value") or data.get("id") or path.stem).strip() or path.stem
        settings = data.get("settings", data)
        if not isinstance(settings, dict):
            continue
        presets[preset_id] = _resolve_preset_settings(settings)
    return presets


def _resolve_preset_settings(settings: dict[object, object]) -> dict[str, object]:
    return {str(key): _resolve_preset_value(str(key), value) for key, value in settings.items()}


def _resolve_preset_value(key: str, value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    project_root = str(PROJECT_ROOT)
    if "${PROJECT_ROOT}" in text or "$PROJECT_ROOT" in text:
        return text.replace("${PROJECT_ROOT}", project_root).replace("$PROJECT_ROOT", project_root)
    if key in PRESET_PATH_SETTING_KEYS and (text.startswith("models/") or text.startswith("models\\")):
        return str(PROJECT_ROOT / Path(text))
    return value


def _language_pack_dropdown_file(folder_name: str, language_id: str | None = None) -> Path | None:
    for pack_dir in _preferred_language_pack_dirs(language_id):
        path = pack_dir / f"{folder_name}.json"
        if path.is_file():
            return path
    return None


def _language_pack_dirs() -> list[Path]:
    if not LANGUAGE_PACKS_DIR.exists():
        return []
    return sorted(
        (path for path in LANGUAGE_PACKS_DIR.iterdir() if path.is_dir()),
        key=lambda item: item.name.lower(),
    )


def _preferred_language_pack_dirs(language_id: str | None = None) -> list[Path]:
    wanted = str(language_id or _configured_gui_language() or "").strip().lower()
    packs = _language_pack_dirs()
    preferred: list[Path] = []
    if wanted:
        for pack_dir in packs:
            option = _read_gui_language_pack(pack_dir)
            ids = {pack_dir.name.lower()}
            if option is not None:
                ids.add(option.id.lower())
            if wanted in ids:
                preferred.append(pack_dir)
    for fallback in LANGUAGE_PACK_FALLBACKS:
        for pack_dir in packs:
            option = _read_gui_language_pack(pack_dir)
            ids = {pack_dir.name.lower()}
            if option is not None:
                ids.add(option.id.lower())
            if fallback in ids and pack_dir not in preferred:
                preferred.append(pack_dir)
    preferred.extend(pack_dir for pack_dir in packs if pack_dir not in preferred)
    return preferred


def _configured_gui_language() -> str:
    settings_path = CONFIG_DIR / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return "vi"
    if not isinstance(data, dict):
        return "vi"
    return str(data.get("gui_language") or "vi").strip() or "vi"


def _read_language_pack_data(pack_dir: Path) -> dict | None:
    for name in ("language.json", "metadata.json", "ui.json"):
        path = pack_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def _read_gui_language_pack(pack_dir: Path) -> RuntimeOption | None:
    data = _read_language_pack_data(pack_dir)
    if not isinstance(data, dict):
        return None
    language_id = str(data.get("id") or data.get("code") or pack_dir.name).strip() or pack_dir.name
    name = str(data.get("name") or data.get("label") or language_id).strip() or language_id
    return RuntimeOption(language_id, name)


def _read_gui_language_file(path: Path) -> RuntimeOption | None:
    language_id = path.stem.strip()
    if not language_id:
        return None
    name = language_id
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                language_id = str(data.get("id") or data.get("code") or language_id).strip() or language_id
                name = str(data.get("name") or data.get("label") or name).strip() or name
        except Exception:
            pass
    else:
        try:
            first_line = path.read_text(encoding="utf-8-sig").splitlines()[0].strip()
            if first_line:
                name = first_line
        except Exception:
            pass
    return RuntimeOption(language_id, name)


def _unique_options(options: list[RuntimeOption]) -> list[RuntimeOption]:
    unique: list[RuntimeOption] = []
    seen: set[str] = set()
    for option in options:
        if option.id in seen:
            continue
        seen.add(option.id)
        unique.append(option)
    return unique


def available_local_llm_options() -> list[RuntimeOption]:
    roots = [TRANSCRIPT_CLEANUP_MODELS_PATH]
    options: list[RuntimeOption] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
            if path.is_file() and path.suffix.lower() == ".gguf":
                if _looks_like_tts_model(path):
                    continue
                _append_model_option(options, seen, path, path.stem)
            elif path.is_dir() and _looks_like_hf_causal_lm(path):
                _append_model_option(options, seen, path, path.name)
    return options


def _append_model_option(options: list[RuntimeOption], seen: set[str], path: Path, name: str) -> None:
    model_id = str(path.resolve())
    if model_id in seen:
        return
    seen.add(model_id)
    options.append(RuntimeOption(model_id, name))


def _looks_like_hf_causal_lm(path: Path) -> bool:
    config_path = path / "config.json"
    tokenizer_path = path / "tokenizer.json"
    if not config_path.exists() or not tokenizer_path.exists():
        return False
    return (
        any(path.glob("*.safetensors"))
        or any(path.glob("*.bin"))
        or any(path.glob("*.gguf"))
        or any(path.glob("model-*"))
    )


def _looks_like_tts_model(path: Path) -> bool:
    lowered = str(path).lower()
    return "vieneu" in lowered or "tts" in lowered


def _scan_tessdata_languages() -> set[str]:
    tessdata = OCR_MODELS_PATH / "tessdata"
    if not tessdata.exists():
        return set()
    return {
        TESSDATA_TO_LANGUAGE.get(path.stem, path.stem) for path in tessdata.glob("*.traineddata") if path.stem != "osd"
    }


def _scan_marian_languages(*, include_auto: bool) -> set[str]:
    root = TRANSLATION_MODELS_PATH / "marian"
    if not root.exists():
        return set()
    codes: set[str] = set()
    for path in root.iterdir():
        if not path.is_dir() or "-" not in path.name:
            continue
        source, target = path.name.split("-", 1)
        if include_auto:
            codes.add(source)
        codes.add(target)
    return codes
