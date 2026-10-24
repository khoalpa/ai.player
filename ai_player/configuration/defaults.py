import math
import os
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent
AI_PLAYER_DIR = CORE_DIR.parent
PACKAGE_ROOT = AI_PLAYER_DIR
RESOURCE_ROOT = PACKAGE_ROOT / "resources"


def _resolve_project_root() -> Path:
    configured = os.getenv("AI_PLAYER_PROJECT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        portable_root = executable_dir.parent
        if executable_dir.name.casefold() == "ai player" and _looks_like_portable_root(portable_root):
            return portable_root
        return executable_dir

    return AI_PLAYER_DIR.parent


def _looks_like_portable_root(path: Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in (
            "Run AI Player.bat",
            "models",
            "data",
            "tools",
        )
    )


PROJECT_ROOT = _resolve_project_root()
MODEL_ROOT = PROJECT_ROOT / "models"
ASR_MODELS_PATH = MODEL_ROOT / "asr"
TRANSLATION_MODELS_PATH = MODEL_ROOT / "translation"
OCR_MODELS_PATH = MODEL_ROOT / "ocr"
TTS_MODELS_PATH = MODEL_ROOT / "tts"
SPEAKER_GENDER_MODELS_PATH = MODEL_ROOT / "speaker_gender"
LOCAL_SPEAKER_GENDER_MODEL_PATH = SPEAKER_GENDER_MODELS_PATH / "common-voice-gender-detection"
INTERNAL_VIENEU_MODELS_PATH = TTS_MODELS_PATH / "vieneu"
INTERNAL_VIENEU_V3_PATH = INTERNAL_VIENEU_MODELS_PATH / "v3-turbo"
INTERNAL_VIENEU_PYTHON = str(
    PROJECT_ROOT / ".venv-vieneu" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)
LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH = str(TRANSLATION_MODELS_PATH / "nllb-200-distilled-600M-ct2-int8")
LOCAL_TRANSLATION_MODEL_13B_PATH = str(TRANSLATION_MODELS_PATH / "nllb-200-1.3B")
LOCAL_TRANSLATION_MODEL_PATH = LOCAL_TRANSLATION_MODEL_13B_PATH
LOCAL_WHISPER_MODEL_PATH = str(ASR_MODELS_PATH / "faster-whisper-large-v3")
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
RUNTIME_DIR = DATA_DIR / "tmp"
PRESERVED_ENGLISH_TERMS_FILE = CONFIG_DIR / "preserved_english_terms.txt"
PRESERVED_SOURCE_TERMS_FILE = CONFIG_DIR / "preserved_source_terms.txt"
DEFAULT_DUBBING_BUFFER_SECONDS = 10.0
DEFAULT_ORIGINAL_VOLUME = 0
DEFAULT_DUBBING_VOICE_VOLUME = 100
DEFAULT_PERFORMANCE_PRESET = "balanced"
DEFAULT_ASR_PROVIDER = "faster_whisper"
DEFAULT_OCR_PROVIDER = "tesseract"
DEFAULT_OCR_MODEL_PATH = str(OCR_MODELS_PATH / "tessdata_best")
DEFAULT_PRESERVED_ENGLISH_TERMS = (
    "AI, API, app, browser, cache, chat, cloud, code, CPU, CUDA, database, debug, "
    "driver, email, export, file, folder, GPU, hardware, import, internet, link, "
    "login, model, offline, online, password, plugin, prompt, RAM, server, "
    "software, stream, token, tool, URL, user, video, voice, web, Wi-Fi, Windows"
)
DEFAULT_PRESERVED_SOURCE_TERMS = (
    f"{DEFAULT_PRESERVED_ENGLISH_TERMS}, HTTP, HTTPS, JSON, CLI, CUDA_VISIBLE_DEVICES, "
    "gpt-4.1-mini, Qwen2.5, RTX 4090, pip install, .env, requirements.txt, "
    "先生, 先輩, 後輩, さん, ちゃん, くん, 오빠, 언니, 형, 누나, 선배, 师傅, 江湖"
)


def preserved_english_terms_file_path() -> Path:
    configured = os.getenv("AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE", "").strip()
    return Path(configured) if configured else PRESERVED_ENGLISH_TERMS_FILE


def preserved_source_terms_file_path() -> Path:
    configured = os.getenv("AI_PLAYER_PRESERVED_SOURCE_TERMS_FILE", "").strip()
    if configured:
        return Path(configured)
    legacy = os.getenv("AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE", "").strip()
    return Path(legacy) if legacy else PRESERVED_SOURCE_TERMS_FILE


def ensure_preserved_terms_file() -> Path:
    path = preserved_source_terms_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        legacy_path = preserved_english_terms_file_path()
        if legacy_path.exists():
            path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text(_terms_text(DEFAULT_PRESERVED_SOURCE_TERMS), encoding="utf-8")
    return path


def read_preserved_terms_file() -> str:
    path = ensure_preserved_terms_file()
    return path.read_text(encoding="utf-8").strip()


def write_preserved_terms_file(value: str) -> None:
    path = ensure_preserved_terms_file()
    path.write_text(_terms_text(value), encoding="utf-8")


read_preserved_source_terms_file = read_preserved_terms_file
write_preserved_source_terms_file = write_preserved_terms_file


def _terms_text(value: str) -> str:
    terms = [item.strip() for item in str(value or "").replace(";", ",").replace("\n", ",").split(",") if item.strip()]
    return "\n".join(dict.fromkeys(terms)) + "\n"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (OverflowError, TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (OverflowError, TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
