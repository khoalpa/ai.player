import os
import sys
from dataclasses import dataclass
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent
AI_PLAYER_DIR = CORE_DIR.parent
PROJECT_ROOT = AI_PLAYER_DIR.parent
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


def preserved_english_terms_file_path() -> Path:
    configured = os.getenv("AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE", "").strip()
    return Path(configured) if configured else PRESERVED_ENGLISH_TERMS_FILE


def ensure_preserved_terms_file() -> Path:
    path = preserved_english_terms_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            _terms_text(DEFAULT_PRESERVED_ENGLISH_TERMS),
            encoding="utf-8",
        )
    return path


def read_preserved_terms_file() -> str:
    path = ensure_preserved_terms_file()
    return path.read_text(encoding="utf-8").strip()


def write_preserved_terms_file(value: str) -> None:
    path = ensure_preserved_terms_file()
    path.write_text(_terms_text(value), encoding="utf-8")


def _terms_text(value: str) -> str:
    terms = [item.strip() for item in str(value or "").replace(";", ",").replace("\n", ",").split(",") if item.strip()]
    return "\n".join(dict.fromkeys(terms)) + "\n"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    gui_language: str = os.getenv("AI_PLAYER_GUI_LANGUAGE", "vi")
    runtime_warmup_enabled: bool = _env_bool("AI_PLAYER_PREWARM_RUNTIME", True)
    runtime_warmup_whisper: bool = _env_bool("AI_PLAYER_PREWARM_WHISPER", True)
    runtime_warmup_translation: bool = _env_bool("AI_PLAYER_PREWARM_TRANSLATION", True)
    runtime_warmup_tts: bool = _env_bool("AI_PLAYER_PREWARM_TTS", True)
    video_aspect_ratio: str = os.getenv("AI_PLAYER_VIDEO_ASPECT_RATIO", "16:9")
    playback_video_quality: str = os.getenv("AI_PLAYER_PLAYBACK_VIDEO_QUALITY", "720p")
    video_url_full_cache: bool = _env_bool("AI_PLAYER_VIDEO_URL_FULL_CACHE", True)
    audio_source: str = os.getenv("AI_PLAYER_AUDIO_SOURCE", "original")
    capture_backend: str = os.getenv("AI_PLAYER_CAPTURE_BACKEND", "auto")
    capture_system_device: str = os.getenv("AI_PLAYER_CAPTURE_SYSTEM_DEVICE", "")
    capture_microphone_device: str = os.getenv("AI_PLAYER_CAPTURE_MICROPHONE_DEVICE", "")
    transcript_cleanup_mode: str = os.getenv("AI_PLAYER_TRANSCRIPT_CLEANUP_MODE", "off")
    transcript_cleanup_provider: str = os.getenv(
        "AI_PLAYER_TRANSCRIPT_CLEANUP_PROVIDER",
        "local" if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists() else "ollama",
    )
    transcript_cleanup_model: str = os.getenv(
        "AI_PLAYER_TRANSCRIPT_CLEANUP_MODEL",
        str(LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH) if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists() else "llama3.1",
    )
    transcript_cleanup_api_base: str = os.getenv("AI_PLAYER_TRANSCRIPT_CLEANUP_API_BASE", "http://127.0.0.1:11434")
    transcript_cleanup_api_key: str = os.getenv("AI_PLAYER_TRANSCRIPT_CLEANUP_API_KEY", "")
    transcript_cleanup_timeout_seconds: float = _env_float("AI_PLAYER_TRANSCRIPT_CLEANUP_TIMEOUT_SECONDS", 12.0)
    transcript_path: str = os.getenv("AI_PLAYER_TRANSCRIPT_PATH", "")
    asr_provider: str = os.getenv("AI_PLAYER_ASR_PROVIDER", DEFAULT_ASR_PROVIDER)
    whisper_model: str = os.getenv("AI_PLAYER_WHISPER_MODEL", LOCAL_WHISPER_MODEL_PATH)
    whisper_offline: bool = os.getenv("AI_PLAYER_WHISPER_OFFLINE", "1") == "1"
    whisper_device: str = os.getenv("AI_PLAYER_WHISPER_DEVICE", "auto")
    whisper_compute_type: str = os.getenv("AI_PLAYER_WHISPER_COMPUTE", "int8")
    whisper_beam_size: int = _env_int("AI_PLAYER_WHISPER_BEAM_SIZE", 1)
    whisper_vad_filter: bool = _env_bool("AI_PLAYER_WHISPER_VAD_FILTER", True)
    ocr_provider: str = os.getenv("AI_PLAYER_OCR_PROVIDER", DEFAULT_OCR_PROVIDER)
    ocr_model: str = os.getenv("AI_PLAYER_OCR_MODEL", DEFAULT_OCR_MODEL_PATH)
    ocr_fps: float = _env_float("AI_PLAYER_OCR_FPS", 2.0)
    ocr_crop_top_ratio: float = _env_float("AI_PLAYER_OCR_CROP_TOP_RATIO", 0.58)
    ocr_crop_height_ratio: float = _env_float("AI_PLAYER_OCR_CROP_HEIGHT_RATIO", 0.38)
    ocr_scale: float = _env_float("AI_PLAYER_OCR_SCALE", 2.0)
    ocr_psm: int = _env_int("AI_PLAYER_OCR_PSM", 6)
    ocr_threshold: bool = _env_bool("AI_PLAYER_OCR_THRESHOLD", True)
    ocr_min_confidence: float = _env_float("AI_PLAYER_OCR_MIN_CONFIDENCE", 35.0)
    ocr_merge_similarity: float = _env_float("AI_PLAYER_OCR_MERGE_SIMILARITY", 0.86)
    source_language: str = os.getenv("AI_PLAYER_SOURCE_LANGUAGE", "auto")
    target_language: str = os.getenv("AI_PLAYER_TARGET_LANGUAGE", "vi")
    local_translation_model: str = os.getenv("AI_PLAYER_TRANSLATION_MODEL", LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH)
    local_translation_device: str = os.getenv("AI_PLAYER_TRANSLATION_DEVICE", "auto")
    local_translation_offline: bool = os.getenv("AI_PLAYER_TRANSLATION_OFFLINE", "1") == "1"
    translator_provider: str = os.getenv("AI_PLAYER_TRANSLATOR_PROVIDER", "nllb_ct2")
    performance_preset: str = os.getenv("AI_PLAYER_PERFORMANCE_PRESET", DEFAULT_PERFORMANCE_PRESET)
    export_video_quality: str = os.getenv("AI_PLAYER_EXPORT_VIDEO_QUALITY", "balanced")
    preserve_english_terms: bool = os.getenv("AI_PLAYER_PRESERVE_ENGLISH_TERMS", "1") == "1"
    preserved_english_terms: str = os.getenv(
        "AI_PLAYER_PRESERVED_ENGLISH_TERMS",
        read_preserved_terms_file(),
    )
    preserved_english_terms_file: str = os.getenv(
        "AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE",
        str(preserved_english_terms_file_path()),
    )
    translation_max_tokens: int = _env_int("AI_PLAYER_TRANSLATION_MAX_TOKENS", 152)
    translation_num_beams: int = _env_int("AI_PLAYER_TRANSLATION_BEAMS", 2)
    segment_seconds: int = _env_int("AI_PLAYER_SEGMENT_SECONDS", 6)
    dubbing_start_delay_seconds: float = _env_float("AI_PLAYER_DUBBING_START_DELAY_SECONDS", 0.0)
    dubbing_prebuffer_segments: int = _env_int("AI_PLAYER_DUBBING_PREBUFFER_SEGMENTS", 1)
    dubbing_lookahead_segments: int = _env_int("AI_PLAYER_DUBBING_LOOKAHEAD_SEGMENTS", 2)
    dubbing_min_ready_ahead_seconds: float = _env_float(
        "AI_PLAYER_DUBBING_MIN_READY_AHEAD_SECONDS",
        DEFAULT_DUBBING_BUFFER_SECONDS,
    )
    dubbing_voice_volume: int = _env_int("AI_PLAYER_DUBBING_VOICE_VOLUME", DEFAULT_DUBBING_VOICE_VOLUME)
    dubbing_speed_percent: int = _env_int("AI_PLAYER_DUBBING_SPEED_PERCENT", 5)
    dubbing_auto_match_audio: bool = os.getenv("AI_PLAYER_DUBBING_AUTO_MATCH_AUDIO", "1") == "1"
    dubbing_overlap_policy: str = os.getenv("AI_PLAYER_DUBBING_OVERLAP_POLICY", "smart")
    dubbing_auto_voice_gender: bool = os.getenv("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER", "1") == "1"
    dubbing_auto_voice_gender_mode: str = os.getenv("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER_MODE", "balanced")
    dubbing_speed_min: float = _env_float("AI_PLAYER_DUBBING_SPEED_MIN", 0.9)
    dubbing_speed_max: float = _env_float("AI_PLAYER_DUBBING_SPEED_MAX", 1.22)
    dubbing_volume_gain_min_db: float = _env_float("AI_PLAYER_DUBBING_VOLUME_GAIN_MIN_DB", -8.0)
    dubbing_volume_gain_max_db: float = _env_float("AI_PLAYER_DUBBING_VOLUME_GAIN_MAX_DB", 6.0)
    original_audio_volume: int = _env_int("AI_PLAYER_ORIGINAL_AUDIO_VOLUME", DEFAULT_ORIGINAL_VOLUME)
    original_audio_voice_filter: bool = os.getenv("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER", "1") == "1"
    original_audio_voice_filter_mode: str = os.getenv("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODE", "fast")
    original_audio_voice_filter_model: str = os.getenv("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODEL", "htdemucs")
    original_audio_playback_delay_seconds: int = _env_int("AI_PLAYER_ORIGINAL_AUDIO_PLAYBACK_DELAY_SECONDS", 6)
    dubbing_enabled_by_default: bool = os.getenv("AI_PLAYER_DUBBING_ENABLED_BY_DEFAULT", "0") == "1"
    tts_provider: str = os.getenv("AI_PLAYER_TTS_PROVIDER", "vieneu")
    tts_voice: str = os.getenv("AI_PLAYER_TTS_VOICE", "Bích Ngọc")
    tts_male_voice: str = os.getenv("AI_PLAYER_TTS_MALE_VOICE", "Phạm Tuyên")
    tts_female_voice: str = os.getenv("AI_PLAYER_TTS_FEMALE_VOICE", "Bích Ngọc")
    vieneu_tts_path: str = INTERNAL_VIENEU_TTS_PATH
    vieneu_tts_runtime: str = os.getenv("AI_PLAYER_VIENEU_TTS_RUNTIME", "subprocess")
    vieneu_tts_python: str = os.getenv(
        "AI_PLAYER_VIENEU_TTS_PYTHON",
        sys.executable,
    )
    vieneu_tts_core: str = os.getenv("AI_PLAYER_VIENEU_TTS_CORE", "local")
    vieneu_tts_mode: str = os.getenv("AI_PLAYER_VIENEU_TTS_MODE", "turbo")
    vieneu_tts_api_base: str = os.getenv("AI_PLAYER_VIENEU_TTS_API_BASE", "")
    vieneu_tts_model_name: str = os.getenv(
        "AI_PLAYER_VIENEU_TTS_MODEL_NAME",
        INTERNAL_VIENEU_TURBO_GGUF,
    )
    vieneu_tts_decoder_path: str = os.getenv(
        "AI_PLAYER_VIENEU_TTS_DECODER_PATH",
        "",
    )
    vieneu_tts_encoder_path: str = os.getenv(
        "AI_PLAYER_VIENEU_TTS_ENCODER_PATH",
        "",
    )
    vieneu_tts_standard_codec_path: str = os.getenv(
        "AI_PLAYER_VIENEU_TTS_STANDARD_CODEC_PATH",
        INTERNAL_VIENEU_STANDARD_CODEC,
    )
    vieneu_tts_offline: bool = os.getenv("AI_PLAYER_VIENEU_TTS_OFFLINE", "1") == "1"
    vieneu_tts_device: str = os.getenv("AI_PLAYER_VIENEU_TTS_DEVICE", "auto")
    vieneu_tts_backend: str = os.getenv("AI_PLAYER_VIENEU_TTS_BACKEND", "auto")
    vieneu_tts_temperature: float = _env_float("AI_PLAYER_VIENEU_TTS_TEMPERATURE", 0.55)
    vieneu_tts_max_chars_chunk: int = _env_int("AI_PLAYER_VIENEU_TTS_MAX_CHARS_CHUNK", 140)

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(**_app_config_env_values())


def _app_config_env_values() -> dict[str, object]:
    transcript_cleanup_default = "local" if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists() else "ollama"
    transcript_cleanup_model_default = (
        str(LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH) if LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH.exists() else "llama3.1"
    )
    return {
        "gui_language": os.getenv("AI_PLAYER_GUI_LANGUAGE", "vi"),
        "runtime_warmup_enabled": _env_bool("AI_PLAYER_PREWARM_RUNTIME", True),
        "runtime_warmup_whisper": _env_bool("AI_PLAYER_PREWARM_WHISPER", True),
        "runtime_warmup_translation": _env_bool("AI_PLAYER_PREWARM_TRANSLATION", True),
        "runtime_warmup_tts": _env_bool("AI_PLAYER_PREWARM_TTS", True),
        "video_aspect_ratio": os.getenv("AI_PLAYER_VIDEO_ASPECT_RATIO", "16:9"),
        "playback_video_quality": os.getenv("AI_PLAYER_PLAYBACK_VIDEO_QUALITY", "720p"),
        "video_url_full_cache": _env_bool("AI_PLAYER_VIDEO_URL_FULL_CACHE", True),
        "audio_source": os.getenv("AI_PLAYER_AUDIO_SOURCE", "original"),
        "capture_backend": os.getenv("AI_PLAYER_CAPTURE_BACKEND", "auto"),
        "capture_system_device": os.getenv("AI_PLAYER_CAPTURE_SYSTEM_DEVICE", ""),
        "capture_microphone_device": os.getenv("AI_PLAYER_CAPTURE_MICROPHONE_DEVICE", ""),
        "transcript_cleanup_mode": os.getenv("AI_PLAYER_TRANSCRIPT_CLEANUP_MODE", "off"),
        "transcript_cleanup_provider": os.getenv(
            "AI_PLAYER_TRANSCRIPT_CLEANUP_PROVIDER",
            transcript_cleanup_default,
        ),
        "transcript_cleanup_model": os.getenv(
            "AI_PLAYER_TRANSCRIPT_CLEANUP_MODEL",
            transcript_cleanup_model_default,
        ),
        "transcript_cleanup_api_base": os.getenv(
            "AI_PLAYER_TRANSCRIPT_CLEANUP_API_BASE",
            "http://127.0.0.1:11434",
        ),
        "transcript_cleanup_api_key": os.getenv("AI_PLAYER_TRANSCRIPT_CLEANUP_API_KEY", ""),
        "transcript_cleanup_timeout_seconds": _env_float("AI_PLAYER_TRANSCRIPT_CLEANUP_TIMEOUT_SECONDS", 12.0),
        "transcript_path": os.getenv("AI_PLAYER_TRANSCRIPT_PATH", ""),
        "asr_provider": os.getenv("AI_PLAYER_ASR_PROVIDER", DEFAULT_ASR_PROVIDER),
        "whisper_model": os.getenv("AI_PLAYER_WHISPER_MODEL", LOCAL_WHISPER_MODEL_PATH),
        "whisper_offline": _env_bool("AI_PLAYER_WHISPER_OFFLINE", True),
        "whisper_device": os.getenv("AI_PLAYER_WHISPER_DEVICE", "auto"),
        "whisper_compute_type": os.getenv("AI_PLAYER_WHISPER_COMPUTE", "int8"),
        "whisper_beam_size": _env_int("AI_PLAYER_WHISPER_BEAM_SIZE", 1),
        "whisper_vad_filter": _env_bool("AI_PLAYER_WHISPER_VAD_FILTER", True),
        "ocr_provider": os.getenv("AI_PLAYER_OCR_PROVIDER", DEFAULT_OCR_PROVIDER),
        "ocr_model": os.getenv("AI_PLAYER_OCR_MODEL", DEFAULT_OCR_MODEL_PATH),
        "ocr_fps": _env_float("AI_PLAYER_OCR_FPS", 2.0),
        "ocr_crop_top_ratio": _env_float("AI_PLAYER_OCR_CROP_TOP_RATIO", 0.58),
        "ocr_crop_height_ratio": _env_float("AI_PLAYER_OCR_CROP_HEIGHT_RATIO", 0.38),
        "ocr_scale": _env_float("AI_PLAYER_OCR_SCALE", 2.0),
        "ocr_psm": _env_int("AI_PLAYER_OCR_PSM", 6),
        "ocr_threshold": _env_bool("AI_PLAYER_OCR_THRESHOLD", True),
        "ocr_min_confidence": _env_float("AI_PLAYER_OCR_MIN_CONFIDENCE", 35.0),
        "ocr_merge_similarity": _env_float("AI_PLAYER_OCR_MERGE_SIMILARITY", 0.86),
        "source_language": os.getenv("AI_PLAYER_SOURCE_LANGUAGE", "auto"),
        "target_language": os.getenv("AI_PLAYER_TARGET_LANGUAGE", "vi"),
        "local_translation_model": os.getenv("AI_PLAYER_TRANSLATION_MODEL", LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH),
        "local_translation_device": os.getenv("AI_PLAYER_TRANSLATION_DEVICE", "auto"),
        "local_translation_offline": _env_bool("AI_PLAYER_TRANSLATION_OFFLINE", True),
        "translator_provider": os.getenv("AI_PLAYER_TRANSLATOR_PROVIDER", "nllb_ct2"),
        "performance_preset": os.getenv("AI_PLAYER_PERFORMANCE_PRESET", DEFAULT_PERFORMANCE_PRESET),
        "export_video_quality": os.getenv("AI_PLAYER_EXPORT_VIDEO_QUALITY", "balanced"),
        "preserve_english_terms": _env_bool("AI_PLAYER_PRESERVE_ENGLISH_TERMS", True),
        "preserved_english_terms": os.getenv(
            "AI_PLAYER_PRESERVED_ENGLISH_TERMS",
            read_preserved_terms_file(),
        ),
        "preserved_english_terms_file": os.getenv(
            "AI_PLAYER_PRESERVED_ENGLISH_TERMS_FILE",
            str(preserved_english_terms_file_path()),
        ),
        "translation_max_tokens": _env_int("AI_PLAYER_TRANSLATION_MAX_TOKENS", 152),
        "translation_num_beams": _env_int("AI_PLAYER_TRANSLATION_BEAMS", 2),
        "segment_seconds": _env_int("AI_PLAYER_SEGMENT_SECONDS", 6),
        "dubbing_start_delay_seconds": _env_float("AI_PLAYER_DUBBING_START_DELAY_SECONDS", 0.0),
        "dubbing_prebuffer_segments": _env_int("AI_PLAYER_DUBBING_PREBUFFER_SEGMENTS", 1),
        "dubbing_lookahead_segments": _env_int("AI_PLAYER_DUBBING_LOOKAHEAD_SEGMENTS", 2),
        "dubbing_min_ready_ahead_seconds": _env_float(
            "AI_PLAYER_DUBBING_MIN_READY_AHEAD_SECONDS",
            DEFAULT_DUBBING_BUFFER_SECONDS,
        ),
        "dubbing_voice_volume": _env_int("AI_PLAYER_DUBBING_VOICE_VOLUME", DEFAULT_DUBBING_VOICE_VOLUME),
        "dubbing_speed_percent": _env_int("AI_PLAYER_DUBBING_SPEED_PERCENT", 5),
        "dubbing_auto_match_audio": _env_bool("AI_PLAYER_DUBBING_AUTO_MATCH_AUDIO", True),
        "dubbing_overlap_policy": os.getenv("AI_PLAYER_DUBBING_OVERLAP_POLICY", "smart"),
        "dubbing_auto_voice_gender": _env_bool("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER", True),
        "dubbing_auto_voice_gender_mode": os.getenv("AI_PLAYER_DUBBING_AUTO_VOICE_GENDER_MODE", "balanced"),
        "dubbing_speed_min": _env_float("AI_PLAYER_DUBBING_SPEED_MIN", 0.9),
        "dubbing_speed_max": _env_float("AI_PLAYER_DUBBING_SPEED_MAX", 1.22),
        "dubbing_volume_gain_min_db": _env_float("AI_PLAYER_DUBBING_VOLUME_GAIN_MIN_DB", -8.0),
        "dubbing_volume_gain_max_db": _env_float("AI_PLAYER_DUBBING_VOLUME_GAIN_MAX_DB", 6.0),
        "original_audio_volume": _env_int("AI_PLAYER_ORIGINAL_AUDIO_VOLUME", DEFAULT_ORIGINAL_VOLUME),
        "original_audio_voice_filter": _env_bool("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER", True),
        "original_audio_voice_filter_mode": os.getenv("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODE", "fast"),
        "original_audio_voice_filter_model": os.getenv("AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODEL", "htdemucs"),
        "original_audio_playback_delay_seconds": _env_int("AI_PLAYER_ORIGINAL_AUDIO_PLAYBACK_DELAY_SECONDS", 6),
        "dubbing_enabled_by_default": _env_bool("AI_PLAYER_DUBBING_ENABLED_BY_DEFAULT", False),
        "tts_provider": os.getenv("AI_PLAYER_TTS_PROVIDER", "vieneu"),
        "tts_voice": os.getenv("AI_PLAYER_TTS_VOICE", "Bích Ngọc"),
        "tts_male_voice": os.getenv("AI_PLAYER_TTS_MALE_VOICE", "Phạm Tuyên"),
        "tts_female_voice": os.getenv("AI_PLAYER_TTS_FEMALE_VOICE", "Bích Ngọc"),
        "vieneu_tts_path": INTERNAL_VIENEU_TTS_PATH,
        "vieneu_tts_runtime": os.getenv("AI_PLAYER_VIENEU_TTS_RUNTIME", "subprocess"),
        "vieneu_tts_python": os.getenv("AI_PLAYER_VIENEU_TTS_PYTHON", sys.executable),
        "vieneu_tts_core": os.getenv("AI_PLAYER_VIENEU_TTS_CORE", "local"),
        "vieneu_tts_mode": os.getenv("AI_PLAYER_VIENEU_TTS_MODE", "turbo"),
        "vieneu_tts_api_base": os.getenv("AI_PLAYER_VIENEU_TTS_API_BASE", ""),
        "vieneu_tts_model_name": os.getenv("AI_PLAYER_VIENEU_TTS_MODEL_NAME", INTERNAL_VIENEU_TURBO_GGUF),
        "vieneu_tts_decoder_path": os.getenv("AI_PLAYER_VIENEU_TTS_DECODER_PATH", ""),
        "vieneu_tts_encoder_path": os.getenv("AI_PLAYER_VIENEU_TTS_ENCODER_PATH", ""),
        "vieneu_tts_standard_codec_path": os.getenv(
            "AI_PLAYER_VIENEU_TTS_STANDARD_CODEC_PATH",
            INTERNAL_VIENEU_STANDARD_CODEC,
        ),
        "vieneu_tts_offline": _env_bool("AI_PLAYER_VIENEU_TTS_OFFLINE", True),
        "vieneu_tts_device": os.getenv("AI_PLAYER_VIENEU_TTS_DEVICE", "auto"),
        "vieneu_tts_backend": os.getenv("AI_PLAYER_VIENEU_TTS_BACKEND", "auto"),
        "vieneu_tts_temperature": _env_float("AI_PLAYER_VIENEU_TTS_TEMPERATURE", 0.55),
        "vieneu_tts_max_chars_chunk": _env_int("AI_PLAYER_VIENEU_TTS_MAX_CHARS_CHUNK", 140),
    }
