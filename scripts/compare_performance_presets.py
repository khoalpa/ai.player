from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_player.core.config import DEFAULT_PERFORMANCE_PRESET  # noqa: E402
from ai_player.core.runtime_catalog import available_dropdown_options, load_performance_presets  # noqa: E402


@dataclass(frozen=True)
class PresetComparison:
    preset: str
    label: str
    quality_score: int
    latency_score: float
    startup_wait_seconds: float
    quality_band: str
    latency_band: str
    summary: str


def compare_presets(language: str = "en") -> list[PresetComparison]:
    labels = {
        option.value: option.label for option in available_dropdown_options("performance_presets", language_id=language)
    }
    presets = load_performance_presets()
    rows = [
        analyze_preset(preset_id, labels.get(preset_id, preset_id), settings) for preset_id, settings in presets.items()
    ]
    return sorted(rows, key=lambda row: (row.latency_score, -row.quality_score, row.preset))


def analyze_preset(preset_id: str, label: str, settings: dict[str, object]) -> PresetComparison:
    quality_score = min(100, round(_quality_score(settings)))
    latency_score = round(_latency_score(settings), 1)
    startup_wait = round(_startup_wait_seconds(settings), 1)
    return PresetComparison(
        preset=preset_id,
        label=label,
        quality_score=quality_score,
        latency_score=latency_score,
        startup_wait_seconds=startup_wait,
        quality_band=_quality_band(quality_score),
        latency_band=_latency_band(latency_score),
        summary=_summary(settings),
    )


def _quality_score(settings: dict[str, object]) -> float:
    score = 0.0
    whisper_model = _lower(settings.get("whisper_model"))
    if "large" in whisper_model:
        score += 25
    elif "medium" in whisper_model:
        score += 20
    elif "small" in whisper_model:
        score += 15
    elif "base" in whisper_model:
        score += 10
    else:
        score += 7

    score += min(10, max(1, _number(settings.get("whisper_beam_size"), 1)) * 2)

    translator = _lower(settings.get("translator_provider"))
    translation_model = _lower(settings.get("local_translation_model"))
    if translator == "nllb" and "1.3b" in translation_model:
        score += 25
    elif translator == "nllb":
        score += 20
    elif "ct2" in translator or "ct2" in translation_model:
        score += 16
    elif translator != "none":
        score += 8

    tts_provider = _lower(settings.get("tts_provider"))
    tts_mode = _lower(settings.get("vieneu_tts_mode"))
    if tts_provider == "vieneu" and tts_mode == "standard":
        score += 18
    elif tts_provider == "vieneu":
        score += 12
    elif tts_provider == "edge":
        score += 10

    export_quality = _lower(settings.get("export_video_quality"))
    score += {"compact": 2, "balanced": 5, "high": 8, "archival": 10}.get(export_quality, 4)

    if bool(settings.get("dubbing_auto_match_audio")):
        score += 4
    if bool(settings.get("dubbing_auto_voice_gender")):
        score += 3

    source_filter = _lower(settings.get("original_audio_voice_filter_mode"))
    score += {"ai": 3, "high_quality": 3, "auto": 1}.get(source_filter, 0)
    return score


def _latency_score(settings: dict[str, object]) -> float:
    score = _startup_wait_seconds(settings)

    whisper_model = _lower(settings.get("whisper_model"))
    if "large" in whisper_model:
        score += 8
    elif "medium" in whisper_model:
        score += 5
    elif "small" in whisper_model:
        score += 3
    else:
        score += 2

    whisper_device = _lower(settings.get("whisper_device"))
    if whisper_device == "cuda":
        score -= 1.5
    elif whisper_device == "cpu":
        score += 1.5

    translator = _lower(settings.get("translator_provider"))
    translation_model = _lower(settings.get("local_translation_model"))
    if translator == "nllb" and "1.3b" in translation_model:
        score += 7
    elif translator == "nllb":
        score += 5
    elif "ct2" in translator or "ct2" in translation_model:
        score += 2
    elif translator != "none":
        score += 3

    tts_provider = _lower(settings.get("tts_provider"))
    tts_mode = _lower(settings.get("vieneu_tts_mode"))
    if tts_provider == "vieneu" and tts_mode == "standard":
        score += 5
    elif tts_provider == "vieneu":
        score += 2
    elif tts_provider == "edge":
        score += 1

    if bool(settings.get("dubbing_auto_match_audio")):
        score += 3
    if bool(settings.get("dubbing_auto_voice_gender")):
        score += 2

    source_filter = _lower(settings.get("original_audio_voice_filter_mode"))
    score += {"ai": 5, "high_quality": 5, "auto": 1}.get(source_filter, 0)
    return max(0.0, score)


def _startup_wait_seconds(settings: dict[str, object]) -> float:
    start_delay = _number(settings.get("dubbing_start_delay_seconds"), 0)
    segment_seconds = _number(settings.get("segment_seconds"), 8)
    prebuffer_segments = _number(settings.get("dubbing_prebuffer_segments"), 1)
    minimum_ready = _number(settings.get("dubbing_min_ready_ahead_seconds"), 0)
    return max(minimum_ready, start_delay + segment_seconds * prebuffer_segments)


def _quality_band(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "high"
    if score >= 50:
        return "balanced"
    return "fast"


def _latency_band(score: float) -> str:
    if score <= 15:
        return "low"
    if score <= 30:
        return "medium"
    if score <= 55:
        return "high"
    return "very high"


def _summary(settings: dict[str, object]) -> str:
    whisper_model = Path(str(settings.get("whisper_model") or "")).name or "-"
    translator = str(settings.get("translator_provider") or "-")
    tts_provider = str(settings.get("tts_provider") or "-")
    tts_mode = str(settings.get("vieneu_tts_mode") or "-")
    tts = f"{tts_provider}/{tts_mode}" if tts_provider == "vieneu" else tts_provider
    return f"{whisper_model}, {translator}, {tts}"


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _lower(value: object) -> str:
    return str(value or "").strip().lower()


def _markdown_table(rows: list[PresetComparison]) -> str:
    lines = [
        "| Preset | Quality | Latency | Startup wait | Pipeline |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        marker = " (default)" if row.preset == DEFAULT_PERFORMANCE_PRESET else ""
        lines.append(
            f"| {row.label}{marker} | {row.quality_score} {row.quality_band} | "
            f"{row.latency_score:.1f} {row.latency_band} | {row.startup_wait_seconds:.1f}s | {row.summary} |"
        )
    return "\n".join(lines)


def main() -> int:
    _prefer_utf8_stdout()
    parser = argparse.ArgumentParser(description="Compare AI Player performance preset tradeoffs.")
    parser.add_argument("--language", default="en", help="Language pack for preset labels, e.g. en or vi.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of Markdown.")
    args = parser.parse_args()

    rows = compare_presets(args.language)
    if args.json:
        print(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2))
    else:
        print(_markdown_table(rows))
    return 0


def _prefer_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
