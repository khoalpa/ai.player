from __future__ import annotations

import time
from collections.abc import Callable

from ai_player.core.app_logging import get_logger
from ai_player.core.config import RUNTIME_DIR, AppConfig
from ai_player.core.i18n import ui_text
from ai_player.core.performance import measure_stage
from ai_player.services.transcript_cleanup import TranscriptCleaner
from ai_player.services.translation import effective_translator_provider
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider, normalize_tts_provider, tts_output_suffix
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type,
    effective_whisper_device,
    get_shared_whisper_model,
)

LOGGER = get_logger(__name__)


class RuntimeWarmupCancelled(RuntimeError):
    pass


def warm_runtime_components(
    config: AppConfig,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, float]:
    timings: dict[str, float] = {}
    if not getattr(config, "runtime_warmup_enabled", True):
        return timings

    def check_cancelled() -> None:
        if cancel_callback is not None and cancel_callback():
            raise RuntimeWarmupCancelled("Runtime warm-up cancelled.")

    if getattr(config, "runtime_warmup_whisper", True):
        check_cancelled()
        _emit(progress_callback, ui_text("warmup_loading_whisper", config.gui_language))
        timings["whisper_load_seconds"] = _time_call(lambda: _warm_whisper(config))

    if getattr(config, "runtime_warmup_translation", True) and effective_translator_provider(config) != "none":
        check_cancelled()
        _emit(progress_callback, ui_text("warmup_loading_translation", config.gui_language))
        timings["translation_seconds"] = _time_call(lambda: _warm_translation(config))

    if getattr(config, "transcript_cleanup_mode", "off") != "off":
        check_cancelled()
        _emit(progress_callback, ui_text("warmup_loading_transcript_cleanup", config.gui_language))
        timings["transcript_cleanup_seconds"] = _time_call(lambda: _warm_transcript_cleanup(config))

    if getattr(config, "runtime_warmup_tts", False) and normalize_tts_provider(config.tts_provider) != "none":
        check_cancelled()
        _emit(progress_callback, ui_text("warmup_loading_tts", config.gui_language))
        timings["tts_seconds"] = _time_call(lambda: _warm_tts(config))

    check_cancelled()
    return timings


def has_runtime_warmup_stage(config: AppConfig) -> bool:
    if not getattr(config, "runtime_warmup_enabled", True):
        return False
    if getattr(config, "runtime_warmup_whisper", True):
        return True
    if getattr(config, "runtime_warmup_translation", True) and effective_translator_provider(config) != "none":
        return True
    if getattr(config, "transcript_cleanup_mode", "off") != "off":
        return True
    return getattr(config, "runtime_warmup_tts", False) and normalize_tts_provider(config.tts_provider) != "none"


def _warm_whisper(config: AppConfig) -> None:
    device = effective_whisper_device(config.whisper_device)
    compute_type = effective_whisper_compute_type(config.whisper_compute_type, device)
    try:
        with measure_stage("warmup", "whisper_load", device=device, compute=compute_type):
            get_shared_whisper_model(
                config.whisper_model,
                device=device,
                compute_type=compute_type,
                local_files_only=config.whisper_offline,
            )
    except Exception:
        if device == "cpu" and compute_type == "int8":
            raise
        LOGGER.warning(
            "Whisper warmup failed on %s/%s; retrying on cpu/int8.",
            device,
            compute_type,
            exc_info=True,
        )
        with measure_stage("warmup", "whisper_load", device="cpu", compute="int8"):
            get_shared_whisper_model(
                config.whisper_model,
                device="cpu",
                compute_type="int8",
                local_files_only=config.whisper_offline,
            )


def _warm_translation(config: AppConfig) -> None:
    translator = get_shared_vietnamese_translator(config)
    with measure_stage("warmup", "translation"):
        translator.translate("Hello, this short sentence warms the translation model.", "en")


def _warm_transcript_cleanup(config: AppConfig) -> None:
    cleaner = TranscriptCleaner(config)
    with measure_stage("warmup", "transcript_cleanup"):
        cleaner.clean("Xin chào, đây là câu kiểm tra ngắn.", config.source_language)


def _warm_tts(config: AppConfig) -> None:
    provider = create_tts_provider(config)
    suffix = tts_output_suffix(config.tts_provider)
    output_path = RUNTIME_DIR / f"runtime-warmup.{suffix}"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with measure_stage("warmup", "tts"):
            provider.synthesize("Xin chào.", output_path, voice=config.tts_voice)
    finally:
        provider.close()


def _time_call(callback: Callable[[], None]) -> float:
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
