import os
from dataclasses import dataclass, fields

from ai_player.configuration.defaults import (
    AI_PLAYER_DIR as AI_PLAYER_DIR,
)
from ai_player.configuration.defaults import (
    ASR_MODELS_PATH as ASR_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    CONFIG_DIR as CONFIG_DIR,
)
from ai_player.configuration.defaults import (
    CORE_DIR as CORE_DIR,
)
from ai_player.configuration.defaults import (
    DATA_DIR as DATA_DIR,
)
from ai_player.configuration.defaults import (
    DEFAULT_ASR_PROVIDER as DEFAULT_ASR_PROVIDER,
)
from ai_player.configuration.defaults import (
    DEFAULT_DUBBING_BUFFER_SECONDS as DEFAULT_DUBBING_BUFFER_SECONDS,
)
from ai_player.configuration.defaults import (
    DEFAULT_DUBBING_VOICE_VOLUME as DEFAULT_DUBBING_VOICE_VOLUME,
)
from ai_player.configuration.defaults import (
    DEFAULT_OCR_MODEL_PATH as DEFAULT_OCR_MODEL_PATH,
)
from ai_player.configuration.defaults import (
    DEFAULT_OCR_PROVIDER as DEFAULT_OCR_PROVIDER,
)
from ai_player.configuration.defaults import (
    DEFAULT_ORIGINAL_VOLUME as DEFAULT_ORIGINAL_VOLUME,
)
from ai_player.configuration.defaults import (
    DEFAULT_PERFORMANCE_PRESET as DEFAULT_PERFORMANCE_PRESET,
)
from ai_player.configuration.defaults import (
    DEFAULT_PRESERVED_ENGLISH_TERMS as DEFAULT_PRESERVED_ENGLISH_TERMS,
)
from ai_player.configuration.defaults import (
    DEFAULT_PRESERVED_SOURCE_TERMS as DEFAULT_PRESERVED_SOURCE_TERMS,
)
from ai_player.configuration.defaults import (
    INTERNAL_VIENEU_MODELS_PATH as INTERNAL_VIENEU_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    INTERNAL_VIENEU_PYTHON as INTERNAL_VIENEU_PYTHON,
)
from ai_player.configuration.defaults import (
    INTERNAL_VIENEU_V3_PATH as INTERNAL_VIENEU_V3_PATH,
)
from ai_player.configuration.defaults import (
    LOCAL_SPEAKER_GENDER_MODEL_PATH as LOCAL_SPEAKER_GENDER_MODEL_PATH,
)
from ai_player.configuration.defaults import (
    LOCAL_TRANSLATION_MODEL_13B_PATH as LOCAL_TRANSLATION_MODEL_13B_PATH,
)
from ai_player.configuration.defaults import (
    LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH as LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH,
)
from ai_player.configuration.defaults import (
    LOCAL_TRANSLATION_MODEL_PATH as LOCAL_TRANSLATION_MODEL_PATH,
)
from ai_player.configuration.defaults import (
    LOCAL_WHISPER_MODEL_PATH as LOCAL_WHISPER_MODEL_PATH,
)
from ai_player.configuration.defaults import (
    MODEL_ROOT as MODEL_ROOT,
)
from ai_player.configuration.defaults import (
    OCR_MODELS_PATH as OCR_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    PACKAGE_ROOT as PACKAGE_ROOT,
)
from ai_player.configuration.defaults import (
    PRESERVED_ENGLISH_TERMS_FILE as PRESERVED_ENGLISH_TERMS_FILE,
)
from ai_player.configuration.defaults import (
    PRESERVED_SOURCE_TERMS_FILE as PRESERVED_SOURCE_TERMS_FILE,
)
from ai_player.configuration.defaults import (
    PROJECT_ROOT as PROJECT_ROOT,
)
from ai_player.configuration.defaults import (
    RESOURCE_ROOT as RESOURCE_ROOT,
)
from ai_player.configuration.defaults import (
    RUNTIME_DIR as RUNTIME_DIR,
)
from ai_player.configuration.defaults import (
    SPEAKER_GENDER_MODELS_PATH as SPEAKER_GENDER_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    TRANSLATION_MODELS_PATH as TRANSLATION_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    TTS_MODELS_PATH as TTS_MODELS_PATH,
)
from ai_player.configuration.defaults import (
    _env_bool as _env_bool,
)
from ai_player.configuration.defaults import (
    _env_float as _env_float,
)
from ai_player.configuration.defaults import (
    _env_int as _env_int,
)
from ai_player.configuration.defaults import (
    _looks_like_portable_root as _looks_like_portable_root,
)
from ai_player.configuration.defaults import (
    _resolve_project_root as _resolve_project_root,
)
from ai_player.configuration.defaults import (
    _terms_text as _terms_text,
)
from ai_player.configuration.defaults import (
    ensure_preserved_terms_file as ensure_preserved_terms_file,
)
from ai_player.configuration.defaults import (
    preserved_english_terms_file_path as preserved_english_terms_file_path,
)
from ai_player.configuration.defaults import (
    preserved_source_terms_file_path as preserved_source_terms_file_path,
)
from ai_player.configuration.defaults import (
    read_preserved_source_terms_file as read_preserved_source_terms_file,
)
from ai_player.configuration.defaults import (
    read_preserved_terms_file as read_preserved_terms_file,
)
from ai_player.configuration.defaults import (
    write_preserved_source_terms_file as write_preserved_source_terms_file,
)
from ai_player.configuration.defaults import (
    write_preserved_terms_file as write_preserved_terms_file,
)
from ai_player.configuration.sections import (
    ASRConfig as ASRConfig,
)
from ai_player.configuration.sections import (
    CaptureConfig as CaptureConfig,
)
from ai_player.configuration.sections import (
    DubbingConfig as DubbingConfig,
)
from ai_player.configuration.sections import (
    InterfaceConfig as InterfaceConfig,
)
from ai_player.configuration.sections import (
    OCRConfig as OCRConfig,
)
from ai_player.configuration.sections import (
    PlaybackConfig as PlaybackConfig,
)
from ai_player.configuration.sections import (
    RuntimeConfig as RuntimeConfig,
)
from ai_player.configuration.sections import (
    SourcesConfig as SourcesConfig,
)
from ai_player.configuration.sections import (
    TranslationConfig as TranslationConfig,
)
from ai_player.configuration.sections import (
    TTSConfig as TTSConfig,
)


@dataclass(frozen=True)
class AppConfig(
    InterfaceConfig,
    SourcesConfig,
    RuntimeConfig,
    PlaybackConfig,
    CaptureConfig,
    ASRConfig,
    OCRConfig,
    TranslationConfig,
    DubbingConfig,
    TTSConfig,
):
    """Immutable configuration assembled from independently owned sections.

    Flat field names remain the stable persistence/constructor format.
    Section snapshots narrow the data supplied to individual providers.
    """

    @property
    def interface(self) -> InterfaceConfig:
        return InterfaceConfig(**{f.name: getattr(self, f.name) for f in fields(InterfaceConfig)})

    @property
    def sources(self) -> SourcesConfig:
        return SourcesConfig(**{f.name: getattr(self, f.name) for f in fields(SourcesConfig)})

    @property
    def runtime(self) -> RuntimeConfig:
        return RuntimeConfig(**{f.name: getattr(self, f.name) for f in fields(RuntimeConfig)})

    @property
    def playback(self) -> PlaybackConfig:
        return PlaybackConfig(**{f.name: getattr(self, f.name) for f in fields(PlaybackConfig)})

    @property
    def capture(self) -> CaptureConfig:
        return CaptureConfig(**{f.name: getattr(self, f.name) for f in fields(CaptureConfig)})

    @property
    def asr(self) -> ASRConfig:
        return ASRConfig(**{f.name: getattr(self, f.name) for f in fields(ASRConfig)})

    @property
    def ocr(self) -> OCRConfig:
        return OCRConfig(**{f.name: getattr(self, f.name) for f in fields(OCRConfig)})

    @property
    def translation(self) -> TranslationConfig:
        return TranslationConfig(**{f.name: getattr(self, f.name) for f in fields(TranslationConfig)})

    @property
    def dubbing(self) -> DubbingConfig:
        return DubbingConfig(**{f.name: getattr(self, f.name) for f in fields(DubbingConfig)})

    @property
    def tts(self) -> TTSConfig:
        return TTSConfig(**{f.name: getattr(self, f.name) for f in fields(TTSConfig)})

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
    "video_url_play_after_cache_percent": ("AI_PLAYER_VIDEO_URL_PLAY_AFTER_CACHE_PERCENT", "int"),
    "video_cache_dir": ("AI_PLAYER_VIDEO_CACHE_DIR", "str"),
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
    "asr_language_hints": ("AI_PLAYER_ASR_LANGUAGE_HINTS", "str"),
    "asr_fallback_to_whisper": ("AI_PLAYER_ASR_FALLBACK_TO_WHISPER", "bool"),
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
    "vieneu_tts_model_name": ("AI_PLAYER_VIENEU_TTS_MODEL_NAME", "str"),
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
