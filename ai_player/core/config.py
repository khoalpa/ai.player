import math
import os
import sys
from dataclasses import dataclass, field, fields
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
TRANSCRIPT_CLEANUP_MODELS_PATH = MODEL_ROOT / "transcript_cleanup"
TTS_MODELS_PATH = MODEL_ROOT / "tts"
SPEAKER_GENDER_MODELS_PATH = MODEL_ROOT / "speaker_gender"
LOCAL_SPEAKER_GENDER_MODEL_PATH = SPEAKER_GENDER_MODELS_PATH / "common-voice-gender-detection"
INTERNAL_VIENEU_TTS_PATH = str(AI_PLAYER_DIR / "vieneu_tts")
INTERNAL_VIENEU_MODELS_PATH = TTS_MODELS_PATH / "vieneu"
INTERNAL_VIENEU_TURBO_PATH = INTERNAL_VIENEU_MODELS_PATH / "turbo"
INTERNAL_VIENEU_STANDARD_PATH = INTERNAL_VIENEU_MODELS_PATH / "standard"
LOCAL_TRANSLATION_MODEL_PATH = str(TRANSLATION_MODELS_PATH / "nllb-200-distilled-600M")
LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH = str(TRANSLATION_MODELS_PATH / "nllb-200-distilled-600M-ct2-int8")
LOCAL_TRANSLATION_MODEL_13B_PATH = str(TRANSLATION_MODELS_PATH / "nllb-200-1.3B")
LOCAL_WHISPER_MODEL_PATH = str(ASR_MODELS_PATH / "faster-whisper-base")
LOCAL_TRANSCRIPT_CLEANUP_MODEL_3B_PATH = TRANSCRIPT_CLEANUP_MODELS_PATH / "Qwen2.5-3B-Instruct"
LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH = LOCAL_TRANSCRIPT_CLEANUP_MODEL_3B_PATH
INTERNAL_VIENEU_TURBO_GGUF = str(INTERNAL_VIENEU_TURBO_PATH / "vieneu-tts-v2-turbo.gguf")
INTERNAL_VIENEU_TURBO_DECODER = str(INTERNAL_VIENEU_TURBO_PATH / "vieneu_decoder.onnx")
INTERNAL_VIENEU_TURBO_ENCODER = str(INTERNAL_VIENEU_TURBO_PATH / "vieneu_encoder.onnx")
INTERNAL_VIENEU_STANDARD_GGUF = str(INTERNAL_VIENEU_STANDARD_PATH / "VieNeu-TTS-0_3B-Q4_0.gguf")
INTERNAL_VIENEU_STANDARD_CODEC = str(INTERNAL_VIENEU_STANDARD_PATH / "distill-neucodec")
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
DEFAULT_OCR_MODEL_PATH = str(OCR_MODELS_PATH / "tessdata")
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


@dataclass(frozen=True)
class AppConfig:
    gui_language: str = "vi"
    telegram_blacklisted_item_keys: tuple[str, ...] = ()
    telegram_blacklisted_content_keys: tuple[str, ...] = ()
    telegram_auto_open_videos: bool = True
    telegram_last_url: str = ""
    telegram_last_post_id: str = ""
    telegram_last_search: str = ""
    telegram_last_filter: str = "all"
    telegram_side_panel_visible: bool = True
    telegram_side_panel_sizes: tuple[int, ...] = (1, 1)
    runtime_warmup_enabled: bool = True
    runtime_warmup_whisper: bool = True
    runtime_warmup_translation: bool = True
    runtime_warmup_tts: bool = False
    video_aspect_ratio: str = "16:9"
    playback_video_quality: str = "720p"
    video_url_full_cache: bool = False
    video_url_recent_urls: tuple[str, ...] = ()
    audio_source: str = "original"
    capture_backend: str = "auto"
    capture_system_device: str = ""
    capture_microphone_device: str = ""
    transcript_cleanup_mode: str = "off"
    transcript_cleanup_provider: str = field(
        default_factory=lambda: "local" if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists() else "ollama"
    )
    transcript_cleanup_model: str = field(
        default_factory=lambda: str(LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH)
        if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists()
        else "llama3.1"
    )
    transcript_cleanup_api_base: str = "http://127.0.0.1:11434"
    transcript_cleanup_api_key: str = ""
    transcript_cleanup_timeout_seconds: float = 12.0
    transcript_path: str = ""
    asr_provider: str = DEFAULT_ASR_PROVIDER
    asr_api_base: str = ""
    asr_api_key: str = ""
    asr_timeout_seconds: float = 600.0
    whisper_model: str = LOCAL_WHISPER_MODEL_PATH
    whisper_offline: bool = True
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 1
    whisper_vad_filter: bool = True
    ocr_provider: str = DEFAULT_OCR_PROVIDER
    ocr_model: str = DEFAULT_OCR_MODEL_PATH
    ocr_api_base: str = ""
    ocr_api_key: str = ""
    ocr_api_region: str = ""
    ocr_timeout_seconds: float = 30.0
    ocr_fps: float = 2.0
    ocr_crop_top_ratio: float = 0.58
    ocr_crop_height_ratio: float = 0.38
    ocr_scale: float = 2.0
    ocr_psm: int = 6
    ocr_threshold: bool = True
    ocr_min_confidence: float = 35.0
    ocr_merge_similarity: float = 0.86
    source_language: str = "auto"
    target_language: str = "vi"
    local_translation_model: str = LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH
    local_translation_device: str = "auto"
    local_translation_offline: bool = True
    translator_provider: str = "nllb_ct2"
    translator_api_base: str = ""
    translator_api_key: str = ""
    translator_api_region: str = ""
    translator_timeout_seconds: float = 30.0
    performance_preset: str = DEFAULT_PERFORMANCE_PRESET
    export_video_quality: str = "balanced"
    preserve_source_terms: bool = True
    preserved_source_terms: str = field(default_factory=read_preserved_source_terms_file)
    preserved_source_terms_file: str = field(default_factory=lambda: str(preserved_source_terms_file_path()))
    preserve_english_terms: bool = True
    preserved_english_terms: str = field(default_factory=read_preserved_terms_file)
    preserved_english_terms_file: str = field(default_factory=lambda: str(preserved_english_terms_file_path()))
    translation_max_tokens: int = 152
    translation_num_beams: int = 1
    segment_seconds: int = 6
    dubbing_start_delay_seconds: float = 0.0
    dubbing_prebuffer_segments: int = 1
    dubbing_lookahead_segments: int = 2
    dubbing_min_ready_ahead_seconds: float = DEFAULT_DUBBING_BUFFER_SECONDS
    dubbing_voice_volume: int = DEFAULT_DUBBING_VOICE_VOLUME
    dubbing_speed_percent: int = 0
    dubbing_auto_match_audio: bool = False
    dubbing_overlap_policy: str = "smart"
    dubbing_auto_voice_gender: bool = False
    dubbing_auto_voice_gender_mode: str = "balanced"
    speaker_gender_provider: str = "local"
    speaker_gender_api_base: str = ""
    speaker_gender_api_key: str = ""
    speaker_gender_timeout_seconds: float = 20.0
    speaker_gender_model: str = field(default_factory=lambda: str(LOCAL_SPEAKER_GENDER_MODEL_PATH))
    dubbing_speed_min: float = 0.92
    dubbing_speed_max: float = 1.12
    dubbing_volume_gain_min_db: float = -8.0
    dubbing_volume_gain_max_db: float = 6.0
    original_audio_volume: int = DEFAULT_ORIGINAL_VOLUME
    original_audio_voice_filter: bool = False
    original_audio_voice_filter_mode: str = "fast"
    original_audio_voice_filter_model: str = "htdemucs"
    original_audio_playback_delay_seconds: int = 6
    dubbing_enabled_by_default: bool = False
    tts_provider: str = "vieneu"
    tts_voice: str = "Thục Đoan"
    tts_male_voice: str = "Xuân Vĩnh"
    tts_female_voice: str = "Thục Đoan"
    tts_api_base: str = ""
    tts_api_key: str = ""
    tts_api_secret: str = ""
    tts_api_region: str = ""
    tts_model: str = ""
    tts_timeout_seconds: float = 30.0
    vieneu_tts_path: str = INTERNAL_VIENEU_TTS_PATH
    vieneu_tts_runtime: str = "subprocess"
    vieneu_tts_python: str = field(default_factory=lambda: sys.executable)
    vieneu_tts_core: str = "local"
    vieneu_tts_mode: str = "turbo"
    vieneu_tts_api_base: str = ""
    vieneu_tts_model_name: str = INTERNAL_VIENEU_TURBO_GGUF
    vieneu_tts_decoder_path: str = ""
    vieneu_tts_encoder_path: str = ""
    vieneu_tts_standard_codec_path: str = INTERNAL_VIENEU_STANDARD_CODEC
    vieneu_tts_offline: bool = True
    vieneu_tts_device: str = "auto"
    vieneu_tts_backend: str = "auto"
    vieneu_tts_temperature: float = 0.55
    vieneu_tts_max_chars_chunk: int = 140

    @classmethod
    def from_env(cls) -> "AppConfig":
        base = cls()
        return cls(**_app_config_env_values(base))


_APP_CONFIG_ENV_FIELDS = {
    "gui_language": ("AI_PLAYER_GUI_LANGUAGE", "str"),
    "runtime_warmup_enabled": ("AI_PLAYER_PREWARM_RUNTIME", "bool"),
    "runtime_warmup_whisper": ("AI_PLAYER_PREWARM_WHISPER", "bool"),
    "runtime_warmup_translation": ("AI_PLAYER_PREWARM_TRANSLATION", "bool"),
    "runtime_warmup_tts": ("AI_PLAYER_PREWARM_TTS", "bool"),
    "video_aspect_ratio": ("AI_PLAYER_VIDEO_ASPECT_RATIO", "str"),
    "playback_video_quality": ("AI_PLAYER_PLAYBACK_VIDEO_QUALITY", "str"),
    "video_url_full_cache": ("AI_PLAYER_VIDEO_URL_FULL_CACHE", "bool"),
    "audio_source": ("AI_PLAYER_AUDIO_SOURCE", "str"),
    "capture_backend": ("AI_PLAYER_CAPTURE_BACKEND", "str"),
    "capture_system_device": ("AI_PLAYER_CAPTURE_SYSTEM_DEVICE", "str"),
    "capture_microphone_device": ("AI_PLAYER_CAPTURE_MICROPHONE_DEVICE", "str"),
    "transcript_cleanup_mode": ("AI_PLAYER_TRANSCRIPT_CLEANUP_MODE", "str"),
    "transcript_cleanup_provider": ("AI_PLAYER_TRANSCRIPT_CLEANUP_PROVIDER", "str"),
    "transcript_cleanup_model": ("AI_PLAYER_TRANSCRIPT_CLEANUP_MODEL", "str"),
    "transcript_cleanup_api_base": ("AI_PLAYER_TRANSCRIPT_CLEANUP_API_BASE", "str"),
    "transcript_cleanup_api_key": ("AI_PLAYER_TRANSCRIPT_CLEANUP_API_KEY", "str"),
    "transcript_cleanup_timeout_seconds": ("AI_PLAYER_TRANSCRIPT_CLEANUP_TIMEOUT_SECONDS", "float"),
    "transcript_path": ("AI_PLAYER_TRANSCRIPT_PATH", "str"),
    "asr_provider": ("AI_PLAYER_ASR_PROVIDER", "str"),
    "asr_api_base": ("AI_PLAYER_ASR_API_BASE", "str"),
    "asr_api_key": ("AI_PLAYER_ASR_API_KEY", "str"),
    "asr_timeout_seconds": ("AI_PLAYER_ASR_TIMEOUT_SECONDS", "float"),
    "whisper_model": ("AI_PLAYER_WHISPER_MODEL", "str"),
    "whisper_offline": ("AI_PLAYER_WHISPER_OFFLINE", "bool"),
    "whisper_device": ("AI_PLAYER_WHISPER_DEVICE", "str"),
    "whisper_compute_type": ("AI_PLAYER_WHISPER_COMPUTE", "str"),
    "whisper_beam_size": ("AI_PLAYER_WHISPER_BEAM_SIZE", "int"),
    "whisper_vad_filter": ("AI_PLAYER_WHISPER_VAD_FILTER", "bool"),
    "ocr_provider": ("AI_PLAYER_OCR_PROVIDER", "str"),
    "ocr_model": ("AI_PLAYER_OCR_MODEL", "str"),
    "ocr_api_base": ("AI_PLAYER_OCR_API_BASE", "str"),
    "ocr_api_key": ("AI_PLAYER_OCR_API_KEY", "str"),
    "ocr_api_region": ("AI_PLAYER_OCR_API_REGION", "str"),
    "ocr_timeout_seconds": ("AI_PLAYER_OCR_TIMEOUT_SECONDS", "float"),
    "ocr_fps": ("AI_PLAYER_OCR_FPS", "float"),
    "ocr_crop_top_ratio": ("AI_PLAYER_OCR_CROP_TOP_RATIO", "float"),
    "ocr_crop_height_ratio": ("AI_PLAYER_OCR_CROP_HEIGHT_RATIO", "float"),
    "ocr_scale": ("AI_PLAYER_OCR_SCALE", "float"),
    "ocr_psm": ("AI_PLAYER_OCR_PSM", "int"),
    "ocr_threshold": ("AI_PLAYER_OCR_THRESHOLD", "bool"),
    "ocr_min_confidence": ("AI_PLAYER_OCR_MIN_CONFIDENCE", "float"),
    "ocr_merge_similarity": ("AI_PLAYER_OCR_MERGE_SIMILARITY", "float"),
    "source_language": ("AI_PLAYER_SOURCE_LANGUAGE", "str"),
    "target_language": ("AI_PLAYER_TARGET_LANGUAGE", "str"),
    "local_translation_model": ("AI_PLAYER_TRANSLATION_MODEL", "str"),
    "local_translation_device": ("AI_PLAYER_TRANSLATION_DEVICE", "str"),
    "local_translation_offline": ("AI_PLAYER_TRANSLATION_OFFLINE", "bool"),
    "translator_provider": ("AI_PLAYER_TRANSLATOR_PROVIDER", "str"),
    "translator_api_base": ("AI_PLAYER_TRANSLATOR_API_BASE", "str"),
    "translator_api_key": ("AI_PLAYER_TRANSLATOR_API_KEY", "str"),
    "translator_api_region": ("AI_PLAYER_TRANSLATOR_API_REGION", "str"),
    "translator_timeout_seconds": ("AI_PLAYER_TRANSLATOR_TIMEOUT_SECONDS", "float"),
    "performance_preset": ("AI_PLAYER_PERFORMANCE_PRESET", "str"),
    "export_video_quality": ("AI_PLAYER_EXPORT_VIDEO_QUALITY", "str"),
    "preserve_source_terms": ("AI_PLAYER_PRESERVE_SOURCE_TERMS", "bool"),
    "preserved_source_terms": ("AI_PLAYER_PRESERVED_SOURCE_TERMS", "str"),
    "preserved_source_terms_file": ("AI_PLAYER_PRESERVED_SOURCE_TERMS_FILE", "str"),
    "preserve_english_terms": ("AI_PLAYER_PRESERVE_ENGLISH_TERMS", "bool"),
    "preserved_english_terms": ("AI_PLAYER_PRESERVED_ENGLISH_TERMS", "str"),
    "preserved_english_terms_file": ("AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE", "str"),
    "translation_max_tokens": ("AI_PLAYER_TRANSLATION_MAX_TOKENS", "int"),
    "translation_num_beams": ("AI_PLAYER_TRANSLATION_BEAMS", "int"),
    "segment_seconds": ("AI_PLAYER_SEGMENT_SECONDS", "int"),
    "dubbing_start_delay_seconds": ("AI_PLAYER_DUBBING_START_DELAY_SECONDS", "float"),
    "dubbing_prebuffer_segments": ("AI_PLAYER_DUBBING_PREBUFFER_SEGMENTS", "int"),
    "dubbing_lookahead_segments": ("AI_PLAYER_DUBBING_LOOKAHEAD_SEGMENTS", "int"),
    "dubbing_min_ready_ahead_seconds": ("AI_PLAYER_DUBBING_MIN_READY_AHEAD_SECONDS", "float"),
    "dubbing_voice_volume": ("AI_PLAYER_DUBBING_VOICE_VOLUME", "int"),
    "dubbing_speed_percent": ("AI_PLAYER_DUBBING_SPEED_PERCENT", "int"),
    "dubbing_auto_match_audio": ("AI_PLAYER_DUBBING_AUTO_MATCH_AUDIO", "bool"),
    "dubbing_overlap_policy": ("AI_PLAYER_DUBBING_OVERLAP_POLICY", "str"),
    "dubbing_auto_voice_gender": ("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER", "bool"),
    "dubbing_auto_voice_gender_mode": ("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER_MODE", "str"),
    "speaker_gender_provider": ("AI_PLAYER_SPEAKER_GENDER_PROVIDER", "str"),
    "speaker_gender_api_base": ("AI_PLAYER_SPEAKER_GENDER_API_BASE", "str"),
    "speaker_gender_api_key": ("AI_PLAYER_SPEAKER_GENDER_API_KEY", "str"),
    "speaker_gender_timeout_seconds": ("AI_PLAYER_SPEAKER_GENDER_TIMEOUT_SECONDS", "float"),
    "speaker_gender_model": ("AI_PLAYER_SPEAKER_GENDER_AI_MODEL", "str"),
    "dubbing_speed_min": ("AI_PLAYER_DUBBING_SPEED_MIN", "float"),
    "dubbing_speed_max": ("AI_PLAYER_DUBBING_SPEED_MAX", "float"),
    "dubbing_volume_gain_min_db": ("AI_PLAYER_DUBBING_VOLUME_GAIN_MIN_DB", "float"),
    "dubbing_volume_gain_max_db": ("AI_PLAYER_DUBBING_VOLUME_GAIN_MAX_DB", "float"),
    "original_audio_volume": ("AI_PLAYER_ORIGINAL_AUDIO_VOLUME", "int"),
    "original_audio_voice_filter": ("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER", "bool"),
    "original_audio_voice_filter_mode": ("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODE", "str"),
    "original_audio_voice_filter_model": ("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODEL", "str"),
    "original_audio_playback_delay_seconds": ("AI_PLAYER_ORIGINAL_AUDIO_PLAYBACK_DELAY_SECONDS", "int"),
    "dubbing_enabled_by_default": ("AI_PLAYER_DUBBING_ENABLED_BY_DEFAULT", "bool"),
    "tts_provider": ("AI_PLAYER_TTS_PROVIDER", "str"),
    "tts_voice": ("AI_PLAYER_TTS_VOICE", "str"),
    "tts_male_voice": ("AI_PLAYER_TTS_MALE_VOICE", "str"),
    "tts_female_voice": ("AI_PLAYER_TTS_FEMALE_VOICE", "str"),
    "tts_api_base": ("AI_PLAYER_TTS_API_BASE", "str"),
    "tts_api_key": ("AI_PLAYER_TTS_API_KEY", "str"),
    "tts_api_secret": ("AI_PLAYER_TTS_API_SECRET", "str"),
    "tts_api_region": ("AI_PLAYER_TTS_API_REGION", "str"),
    "tts_model": ("AI_PLAYER_TTS_MODEL", "str"),
    "tts_timeout_seconds": ("AI_PLAYER_TTS_TIMEOUT_SECONDS", "float"),
    "vieneu_tts_runtime": ("AI_PLAYER_VIENEU_TTS_RUNTIME", "str"),
    "vieneu_tts_python": ("AI_PLAYER_VIENEU_TTS_PYTHON", "str"),
    "vieneu_tts_core": ("AI_PLAYER_VIENEU_TTS_CORE", "str"),
    "vieneu_tts_mode": ("AI_PLAYER_VIENEU_TTS_MODE", "str"),
    "vieneu_tts_api_base": ("AI_PLAYER_VIENEU_TTS_API_BASE", "str"),
    "vieneu_tts_model_name": ("AI_PLAYER_VIENEU_TTS_MODEL_NAME", "str"),
    "vieneu_tts_decoder_path": ("AI_PLAYER_VIENEU_TTS_DECODER_PATH", "str"),
    "vieneu_tts_encoder_path": ("AI_PLAYER_VIENEU_TTS_ENCODER_PATH", "str"),
    "vieneu_tts_standard_codec_path": ("AI_PLAYER_VIENEU_TTS_STANDARD_CODEC_PATH", "str"),
    "vieneu_tts_offline": ("AI_PLAYER_VIENEU_TTS_OFFLINE", "bool"),
    "vieneu_tts_device": ("AI_PLAYER_VIENEU_TTS_DEVICE", "str"),
    "vieneu_tts_backend": ("AI_PLAYER_VIENEU_TTS_BACKEND", "str"),
    "vieneu_tts_temperature": ("AI_PLAYER_VIENEU_TTS_TEMPERATURE", "float"),
    "vieneu_tts_max_chars_chunk": ("AI_PLAYER_VIENEU_TTS_MAX_CHARS_CHUNK", "int"),
}


def _app_config_env_values(base: AppConfig | None = None) -> dict[str, object]:
    config = base or AppConfig()
    values = {config_field.name: getattr(config, config_field.name) for config_field in fields(AppConfig)}
    for field_name, (env_name, value_type) in _APP_CONFIG_ENV_FIELDS.items():
        default = getattr(config, field_name)
        values[field_name] = _env_value(env_name, value_type, default)
    if "AI_PLAYER_PRESERVE_SOURCE_TERMS" not in os.environ and "AI_PLAYER_PRESERVE_ENGLISH_TERMS" in os.environ:
        values["preserve_source_terms"] = values["preserve_english_terms"]
    if "AI_PLAYER_PRESERVED_SOURCE_TERMS" not in os.environ and "AI_PLAYER_PRESERVED_ENGLISH_TERMS" in os.environ:
        values["preserved_source_terms"] = values["preserved_english_terms"]
    if (
        "AI_PLAYER_PRESERVED_SOURCE_TERMS_FILE" not in os.environ
        and "AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE" in os.environ
    ):
        values["preserved_source_terms_file"] = values["preserved_english_terms_file"]
    values["preserve_english_terms"] = values["preserve_source_terms"]
    values["preserved_english_terms"] = values["preserved_source_terms"]
    values["preserved_english_terms_file"] = values["preserved_source_terms_file"]
    return values


def _env_value(name: str, value_type: str, default: object) -> object:
    if value_type == "bool":
        return _env_bool(name, bool(default))
    if value_type == "int":
        return _env_int(name, int(default))
    if value_type == "float":
        return _env_float(name, float(default))
    return os.getenv(name, str(default))
