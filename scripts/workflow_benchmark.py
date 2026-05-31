from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from importlib import metadata
from pathlib import Path

from ai_player.core.cli_encoding import prefer_utf8_stdio
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

BENCHMARK_SCHEMA_VERSION = 1


def _time_call(callback):
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def main() -> int:
    prefer_utf8_stdio(sys.stdout, sys.stderr)
    parser = argparse.ArgumentParser(description="Small ASR/translation/TTS benchmark for AI Player.")
    parser.add_argument("--audio", default="", help="Optional audio/video file for ASR timing.")
    parser.add_argument("--text", default="Hello, this is an AI Player benchmark.", help="Text to translate and speak.")
    parser.add_argument("--output", default=str(RUNTIME_DIR / "workflow_benchmark.json"), help="JSON result path.")
    parser.add_argument("--source-language", default="en", help="Source language hint for translation/ASR.")
    parser.add_argument("--baseline", default="", help="Optional previous JSON result to compare timings against.")
    parser.add_argument(
        "--max-regression-percent",
        type=float,
        default=35.0,
        help="Allowed timing increase when --baseline is provided.",
    )
    parser.add_argument("--skip-asr", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--skip-tts", action="store_true")
    args = parser.parse_args()

    config = AppConfig.from_env()
    timings: dict[str, float] = {}
    details: dict[str, object] = {}
    asr_device = ""

    if args.audio and not args.skip_asr:
        audio_path = Path(args.audio)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        device = effective_whisper_device(config.whisper_device)
        asr_device = device
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

    result = build_benchmark_result(
        config=config,
        audio=args.audio,
        source_language=args.source_language,
        timings=timings,
        details=details,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if args.baseline:
        regressions = compare_timing_regressions(
            result,
            json.loads(Path(args.baseline).read_text(encoding="utf-8-sig")),
            max_regression_percent=args.max_regression_percent,
        )
        if regressions:
            for regression in regressions:
                print(regression, file=sys.stderr)
            return 2
    _exit_cleanly_after_cuda_asr(asr_device)
    return 0


def build_benchmark_result(
    *,
    config: AppConfig,
    audio: str,
    source_language: str,
    timings: dict[str, float],
    details: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "app_version": _app_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "preset": config.performance_preset,
        "audio": audio,
        "source_language": source_language,
        "config": {
            "asr_provider": config.asr_provider,
            "whisper_model": config.whisper_model,
            "whisper_device": config.whisper_device,
            "whisper_compute_type": config.whisper_compute_type,
            "translator_provider": config.translator_provider,
            "local_translation_model": config.local_translation_model,
            "tts_provider": config.tts_provider,
            "tts_voice": config.tts_voice,
            "vieneu_tts_mode": config.vieneu_tts_mode,
            "vieneu_tts_device": config.vieneu_tts_device,
        },
        "timings": dict(sorted(timings.items())),
        "details": dict(sorted(details.items())),
    }


def compare_timing_regressions(
    current: dict[str, object],
    baseline: dict[str, object],
    *,
    max_regression_percent: float = 35.0,
) -> list[str]:
    current_timings = current.get("timings") if isinstance(current, dict) else {}
    baseline_timings = baseline.get("timings") if isinstance(baseline, dict) else {}
    if not isinstance(current_timings, dict) or not isinstance(baseline_timings, dict):
        return ["Benchmark regression check requires 'timings' objects in both JSON files."]

    allowed_ratio = 1.0 + max(0.0, float(max_regression_percent or 0.0)) / 100.0
    regressions = []
    for key, baseline_value in sorted(baseline_timings.items()):
        if key not in current_timings:
            continue
        baseline_seconds = _positive_float(baseline_value)
        current_seconds = _positive_float(current_timings.get(key))
        if baseline_seconds <= 0.0 or current_seconds <= 0.0:
            continue
        threshold = baseline_seconds * allowed_ratio
        if current_seconds > threshold:
            regressions.append(
                f"{key} regressed: {current_seconds:.3f}s > {threshold:.3f}s "
                f"({baseline_seconds:.3f}s baseline, +{max_regression_percent:.1f}% allowed)"
            )
    return regressions


def _positive_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0.0 else 0.0


def _app_version() -> str:
    try:
        return metadata.version("ai-player")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _exit_cleanly_after_cuda_asr(device: str) -> None:
    if str(device or "").strip().lower() != "cuda":
        return
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
