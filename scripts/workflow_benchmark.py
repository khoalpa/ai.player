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
from ai_player.services.ffmpeg import probe_duration_seconds
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.tts import create_tts_provider
from ai_player.services.tts_base import normalize_tts_provider, tts_output_suffix
from ai_player.services.whisper_runtime import (
    effective_whisper_compute_type,
    effective_whisper_device,
    get_shared_whisper_model,
)

BENCHMARK_SCHEMA_VERSION = 1
DEFAULT_BASELINE_FILE = Path(__file__).resolve().parents[1] / "docs" / "workflow_benchmark_baselines.json"


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
        "--baseline-workflow",
        default="",
        help="Named workflow baseline to compare against, e.g. video_short, transcript, or document.",
    )
    parser.add_argument(
        "--check-baselines",
        action="store_true",
        help="Validate the workflow baseline file and exit without running ASR/translation/TTS.",
    )
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

    if args.check_baselines:
        baselines = load_workflow_baselines(Path(args.baseline) if args.baseline else DEFAULT_BASELINE_FILE)
        print(json.dumps({"workflows": sorted(baselines), "count": len(baselines)}, indent=2))
        return 0

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
            details["tts_output_path"] = str(output_audio)
            details["tts_output_bytes"] = output_audio.stat().st_size if output_audio.exists() else 0
            details["tts_output_duration_seconds"] = (
                probe_duration_seconds(output_audio) if output_audio.exists() else 0.0
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
    print(summarize_benchmark_result(result))
    baseline = {}
    if args.baseline_workflow:
        baseline = load_named_workflow_baseline(
            Path(args.baseline) if args.baseline else DEFAULT_BASELINE_FILE,
            args.baseline_workflow,
        )
    elif args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8-sig"))
    if baseline:
        regressions = compare_timing_regressions(
            result,
            baseline,
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


def summarize_benchmark_result(result: dict[str, object]) -> str:
    timings = result.get("timings") if isinstance(result, dict) else {}
    details = result.get("details") if isinstance(result, dict) else {}
    if not isinstance(timings, dict):
        timings = {}
    if not isinstance(details, dict):
        details = {}

    parts = ["Workflow benchmark summary"]
    for key in ("asr_seconds", "translation_seconds", "tts_seconds"):
        value = _positive_float(timings.get(key))
        if value > 0:
            parts.append(f"{key.removesuffix('_seconds')}: {value:.2f}s")
    if "asr_segments" in details:
        parts.append(f"asr_segments: {int(details.get('asr_segments') or 0)}")
    if details.get("asr_language"):
        parts.append(f"asr_language: {details['asr_language']}")
    duration = _positive_float(details.get("tts_output_duration_seconds"))
    if duration > 0:
        parts.append(f"tts_output_duration: {duration:.2f}s")
    bytes_value = int(details.get("tts_output_bytes") or 0)
    if bytes_value > 0:
        parts.append(f"tts_output_bytes: {bytes_value}")
    return " | ".join(parts)


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


def load_workflow_baselines(path: Path = DEFAULT_BASELINE_FILE) -> dict[str, dict[str, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError(f"Unsupported benchmark baseline schema: {data.get('schema_version')!r}")
    workflows = data.get("workflows")
    if not isinstance(workflows, dict) or not workflows:
        raise ValueError("Benchmark baseline file must contain a non-empty 'workflows' object.")
    parsed: dict[str, dict[str, object]] = {}
    for name, entry in workflows.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Benchmark baseline workflow names must be non-empty strings.")
        if not isinstance(entry, dict):
            raise ValueError(f"Benchmark baseline '{name}' must be an object.")
        result = entry.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"Benchmark baseline '{name}' must contain a result object.")
        _validate_benchmark_result(result, context=name)
        parsed[name] = result
    return parsed


def load_named_workflow_baseline(path: Path, workflow: str) -> dict[str, object]:
    baselines = load_workflow_baselines(path)
    key = str(workflow or "").strip()
    if key not in baselines:
        available = ", ".join(sorted(baselines))
        raise ValueError(f"Unknown benchmark workflow '{workflow}'. Available: {available}")
    return baselines[key]


def _validate_benchmark_result(result: dict[str, object], *, context: str) -> None:
    if result.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise ValueError(f"Benchmark baseline '{context}' has an unsupported result schema.")
    timings = result.get("timings")
    if not isinstance(timings, dict) or not timings:
        raise ValueError(f"Benchmark baseline '{context}' must include timings.")
    for key, value in timings.items():
        if not str(key).endswith("_seconds") or _positive_float(value) <= 0.0:
            raise ValueError(f"Benchmark baseline '{context}' has invalid timing '{key}'.")


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
