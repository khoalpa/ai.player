from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ai_player.core.config import RUNTIME_DIR, AppConfig
from ai_player.services.translation import PassthroughTranslator
from ai_player.services.tts import (
    create_tts_provider,
    normalize_tts_provider,
    tts_output_suffix,
)


def _time_call(callback):
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description="Small ASR/translation/TTS benchmark for AI Player.")
    parser.add_argument("--audio", default="", help="Optional audio/video file; ASR is skipped in the recovery script.")
    parser.add_argument("--text", default="Hello, this is an AI Player benchmark.", help="Text to translate and speak.")
    parser.add_argument("--output", default=str(RUNTIME_DIR / "workflow_benchmark.json"), help="JSON result path.")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--skip-tts", action="store_true")
    args = parser.parse_args()

    config = AppConfig.from_env()
    timings: dict[str, float] = {}

    if not args.skip_translation:
        translator = PassthroughTranslator()
        timings["translation_seconds"] = _time_call(lambda: translator.translate(args.text, "en"))

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
        "recovery_note": "ASR timing is not implemented in the reconstructed helper.",
        "audio": args.audio,
        "timings": timings,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
