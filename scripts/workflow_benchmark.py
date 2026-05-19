from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ai_player.core.config import RUNTIME_DIR, AppConfig
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import (
    create_tts_provider,
    normalize_tts_provider,
    tts_output_suffix,
)
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type,
    effective_whisper_device,
    get_shared_whisper_model,
)


def _time_call(callback):
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description="Small ASR/translation/TTS benchmark for AI Player.")
    parser.add_argument("--audio", default="", help="Optional audio/video file for ASR timing.")
    parser.add_argument("--text", default="Hello, this is an AI Player benchmark.", help="Text to translate and speak.")
    parser.add_argument("--output", default=str(RUNTIME_DIR / "workflow_benchmark.json"), help="JSON result path.")
    parser.add_argument("--source-language", default="en", help="Source language hint for translation/ASR.")
    parser.add_argument("--skip-asr", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--skip-tts", action="store_true")
    args = parser.parse_args()

    config = AppConfig.from_env()
    timings: dict[str, float] = {}
    details: dict[str, object] = {}

    if args.audio and not args.skip_asr:
        audio_path = Path(args.audio)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        device = effective_whisper_device(config.whisper_device)
        compute_type = effective_whisper_compute_type(config.whisper_compute_type, device)
        model = get_shared_whisper_model(
            config.whisper_model,
            device=device,
            compute_type=compute_type,
            local_files_only=config.whisper_offline,
        )

        def run_asr() -> None:
            segments, info = model.transcribe(
                str(audio_path),
                beam_size=1,
                vad_filter=True,
                language=None if args.source_language.lower() == "auto" else args.source_language,
            )
            details["asr_segments"] = len([segment for segment in segments if getattr(segment, "text", "").strip()])
            details["asr_language"] = getattr(info, "language", None)

        timings["asr_seconds"] = _time_call(run_asr)

    if not args.skip_translation:
        translator = get_shared_vietnamese_translator(config)
        timings["translation_seconds"] = _time_call(lambda: translator.translate(args.text, args.source_language))

    if not args.skip_tts and normalize_tts_provider(config.tts_provider) != "none":
        provider = create_tts_provider(config)
        suffix = tts_output_suffix(config.tts_provider)
        output_audio = RUNTIME_DIR / f"workflow-benchmark-tts.{suffix}"
        try:
            output_audio.parent.mkdir(parents=True, exist_ok=True)
            timings["tts_seconds"] = _time_call(
                lambda: provider.synthesize(args.text, output_audio, voice=config.tts_voice)
            )
        finally:
            provider.close()

    result = {
        "preset": config.performance_preset,
        "audio": args.audio,
        "timings": timings,
        "details": details,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
