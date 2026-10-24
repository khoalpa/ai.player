from dataclasses import dataclass, field

from ai_player.configuration.defaults import (
    DEFAULT_ASR_PROVIDER,
    DEFAULT_DUBBING_VOICE_VOLUME,
    DEFAULT_OCR_MODEL_PATH,
    DEFAULT_OCR_PROVIDER,
    DEFAULT_ORIGINAL_VOLUME,
    DEFAULT_PERFORMANCE_PRESET,
    INTERNAL_VIENEU_PYTHON,
    INTERNAL_VIENEU_V3_PATH,
    LOCAL_SPEAKER_GENDER_MODEL_PATH,
    LOCAL_TRANSLATION_MODEL_13B_PATH,
    LOCAL_WHISPER_MODEL_PATH,
    preserved_english_terms_file_path,
    preserved_source_terms_file_path,
    read_preserved_source_terms_file,
    read_preserved_terms_file,
)


@dataclass(frozen=True)
class InterfaceConfig:
    gui_language: str = "vi"
    show_advanced_provider_options: bool = False


@dataclass(frozen=True)
class SourcesConfig:
    telegram_blacklisted_item_keys: tuple[str, ...] = ()
    telegram_blacklisted_content_keys: tuple[str, ...] = ()
    telegram_auto_open_videos: bool = True
    telegram_last_url: str = ""
    telegram_last_post_id: str = ""
    telegram_last_search: str = ""
    telegram_last_filter: str = "all"
    telegram_side_panel_visible: bool = True
    telegram_side_panel_sizes: tuple[int, ...] = (1, 1)
    video_url_recent_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeConfig:
    runtime_warmup_enabled: bool = True
    runtime_warmup_whisper: bool = True
    runtime_warmup_translation: bool = True
    runtime_warmup_tts: bool = False
    performance_preset: str = DEFAULT_PERFORMANCE_PRESET


@dataclass(frozen=True)
class PlaybackConfig:
    video_aspect_ratio: str = "16:9"
    playback_video_quality: str = "best"
    video_url_full_cache: bool = True
    video_url_play_after_cache_percent: int = 15
    video_cache_dir: str = ""
    export_video_quality: str = "balanced"
    original_audio_volume: int = DEFAULT_ORIGINAL_VOLUME
    original_audio_voice_filter: bool = False
    original_audio_voice_filter_mode: str = "ai"
    original_audio_voice_filter_model: str = "htdemucs"
    original_audio_playback_delay_seconds: int = 6


@dataclass(frozen=True)
class CaptureConfig:
    audio_source: str = "original"
    capture_backend: str = "auto"
    capture_system_device: str = ""
    capture_microphone_device: str = ""


@dataclass(frozen=True)
class ASRConfig:
    transcript_cleanup_mode: str = "off"
    transcript_cleanup_provider: str = "groq"
    transcript_cleanup_model: str = "openai/gpt-oss-20b"
    transcript_cleanup_api_base: str = ""
    transcript_cleanup_api_key: str = ""
    transcript_cleanup_timeout_seconds: float = 12.0
    transcript_path: str = ""
    asr_provider: str = DEFAULT_ASR_PROVIDER
    asr_api_base: str = ""
    asr_api_key: str = ""
    asr_language_hints: str = ""
    asr_fallback_to_whisper: bool = True
    asr_timeout_seconds: float = 600.0
    whisper_model: str = LOCAL_WHISPER_MODEL_PATH
    whisper_offline: bool = True
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 1
    whisper_vad_filter: bool = True


@dataclass(frozen=True)
class OCRConfig:
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


@dataclass(frozen=True)
class TranslationConfig:
    source_language: str = "auto"
    target_language: str = "vi"
    local_translation_model: str = LOCAL_TRANSLATION_MODEL_13B_PATH
    local_translation_device: str = "auto"
    local_translation_offline: bool = True
    translator_provider: str = "nllb"
    translator_api_base: str = ""
    translator_api_key: str = ""
    translator_api_region: str = ""
    translator_timeout_seconds: float = 30.0
    preserve_source_terms: bool = True
    preserved_source_terms: str = field(default_factory=read_preserved_source_terms_file)
    preserved_source_terms_file: str = field(default_factory=lambda: str(preserved_source_terms_file_path()))
    preserve_english_terms: bool = True
    preserved_english_terms: str = field(default_factory=read_preserved_terms_file)
    preserved_english_terms_file: str = field(default_factory=lambda: str(preserved_english_terms_file_path()))
    translation_max_tokens: int = 192
    translation_num_beams: int = 1


@dataclass(frozen=True)
class DubbingConfig:
    segment_seconds: int = 6
    dubbing_start_delay_seconds: float = 0.0
    dubbing_prebuffer_segments: int = 3
    dubbing_lookahead_segments: int = 3
    dubbing_min_ready_ahead_seconds: float = 15.0
    dubbing_voice_volume: int = DEFAULT_DUBBING_VOICE_VOLUME
    dubbing_speed_percent: int = 0
    dubbing_auto_match_audio: bool = False
    dubbing_overlap_policy: str = "smart"
    dubbing_auto_voice_gender: bool = False
    dubbing_auto_voice_gender_mode: str = "ai"
    speaker_gender_provider: str = "local"
    speaker_gender_api_base: str = ""
    speaker_gender_api_key: str = ""
    speaker_gender_timeout_seconds: float = 20.0
    speaker_gender_model: str = field(default_factory=lambda: str(LOCAL_SPEAKER_GENDER_MODEL_PATH))
    dubbing_speed_min: float = 0.92
    dubbing_speed_max: float = 1.12
    dubbing_volume_gain_min_db: float = -8.0
    dubbing_volume_gain_max_db: float = 6.0
    dubbing_enabled_by_default: bool = False


@dataclass(frozen=True)
class TTSConfig:
    tts_provider: str = "vieneu"
    tts_voice: str = "Thục Đoan"
    tts_male_voice: str = "Minh Triết"
    tts_female_voice: str = "Thục Đoan"
    tts_api_base: str = ""
    tts_api_key: str = ""
    tts_api_secret: str = ""
    tts_api_region: str = ""
    tts_model: str = ""
    tts_timeout_seconds: float = 30.0
    vieneu_tts_runtime: str = "subprocess"
    vieneu_tts_python: str = INTERNAL_VIENEU_PYTHON
    vieneu_tts_core: str = "local"
    vieneu_tts_mode: str = "v3turbo"
    vieneu_tts_model_name: str = str(INTERNAL_VIENEU_V3_PATH)
    vieneu_tts_offline: bool = True
    vieneu_tts_device: str = "auto"
    vieneu_tts_backend: str = "auto"
    vieneu_tts_temperature: float = 0.55
    vieneu_tts_max_chars_chunk: int = 140
