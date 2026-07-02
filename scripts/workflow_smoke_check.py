from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_player.core.cli_encoding import prefer_utf8_stdio
from ai_player.services.ffmpeg import probe_duration_seconds, run_ffprobe

SMOKE_SCHEMA_VERSION = 1
DEFAULT_BASELINE_FILE = PROJECT_ROOT / "docs" / "workflow_smoke_baseline.json"


def main() -> int:
    prefer_utf8_stdio(sys.stdout, sys.stderr)
    parser = argparse.ArgumentParser(description="Check deterministic workflow smoke fixtures.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_FILE), help="Workflow smoke baseline JSON.")
    parser.add_argument("--output", default="", help="Optional JSON metrics output path.")
    args = parser.parse_args()

    baseline = load_smoke_baseline(Path(args.baseline))
    metrics = collect_smoke_metrics(PROJECT_ROOT)
    failures = compare_smoke_metrics(metrics, baseline)
    result = {"schema_version": SMOKE_SCHEMA_VERSION, "metrics": metrics, "failures": failures}
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(summarize_smoke_result(result))
    return 2 if failures else 0


def load_smoke_baseline(path: Path = DEFAULT_BASELINE_FILE) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != SMOKE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported workflow smoke baseline schema: {data.get('schema_version')!r}")
    samples = data.get("samples")
    if not isinstance(samples, dict) or not samples:
        raise ValueError("Workflow smoke baseline must contain a non-empty 'samples' object.")
    return data


def collect_smoke_metrics(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    video_path = project_root / "samples" / "demo-video.mp4"
    transcript_path = project_root / "samples" / "demo-transcript.srt"
    return {
        "samples": {
            "demo_video": media_sample_metrics(video_path, project_root=project_root),
            "demo_transcript": transcript_sample_metrics(transcript_path, project_root=project_root),
        }
    }


def media_sample_metrics(path: Path, *, project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    metrics: dict[str, object] = {
        "path": _relative_path(path, project_root),
        "exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else 0,
        "duration_seconds": probe_duration_seconds(path) if path.exists() else 0.0,
        "has_audio_stream": False,
        "has_video_stream": False,
    }
    if path.exists():
        stream_types = _media_stream_types(path)
        metrics["has_audio_stream"] = "audio" in stream_types
        metrics["has_video_stream"] = "video" in stream_types
    return metrics


def transcript_sample_metrics(path: Path, *, project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    return {
        "path": _relative_path(path, project_root),
        "exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else 0,
        "segment_count": count_srt_segments(text),
    }


def compare_smoke_metrics(metrics: dict[str, object], baseline: dict[str, object]) -> list[str]:
    failures: list[str] = []
    current_samples = metrics.get("samples") if isinstance(metrics, dict) else {}
    expected_samples = baseline.get("samples") if isinstance(baseline, dict) else {}
    if not isinstance(current_samples, dict) or not isinstance(expected_samples, dict):
        return ["Workflow smoke metrics and baseline must contain 'samples' objects."]

    for name, expected in sorted(expected_samples.items()):
        if not isinstance(expected, dict):
            failures.append(f"{name}: baseline entry must be an object.")
            continue
        current = current_samples.get(name)
        if not isinstance(current, dict):
            failures.append(f"{name}: sample metrics are missing.")
            continue
        failures.extend(_compare_sample(name, current, expected))
    return failures


def count_srt_segments(text: str) -> int:
    blocks = [block.strip() for block in str(text or "").replace("\r\n", "\n").split("\n\n")]
    return sum(1 for block in blocks if "-->" in block)


def summarize_smoke_result(result: dict[str, object]) -> str:
    metrics = result.get("metrics") if isinstance(result, dict) else {}
    failures = result.get("failures") if isinstance(result, dict) else []
    samples = metrics.get("samples") if isinstance(metrics, dict) else {}
    if not isinstance(samples, dict):
        samples = {}
    demo_video = samples.get("demo_video") if isinstance(samples.get("demo_video"), dict) else {}
    demo_transcript = samples.get("demo_transcript") if isinstance(samples.get("demo_transcript"), dict) else {}
    parts = [
        "Workflow smoke summary",
        f"demo_video: {float(demo_video.get('duration_seconds') or 0.0):.2f}s",
        f"audio={bool(demo_video.get('has_audio_stream'))}",
        f"video={bool(demo_video.get('has_video_stream'))}",
        f"demo_transcript_segments={int(demo_transcript.get('segment_count') or 0)}",
    ]
    if failures:
        parts.append(f"failures={len(failures)}")
    else:
        parts.append("failures=0")
    return " | ".join(parts)


def _compare_sample(name: str, current: dict[str, object], expected: dict[str, object]) -> list[str]:
    failures = []
    if expected.get("required", True) and not current.get("exists"):
        failures.append(f"{name}: required sample file is missing.")
    for key in ("has_audio_stream", "has_video_stream"):
        if key in expected and bool(current.get(key)) is not bool(expected.get(key)):
            failures.append(f"{name}: expected {key}={expected.get(key)!r}, got {current.get(key)!r}.")
    for key in ("segment_count",):
        if key in expected and int(current.get(key) or 0) != int(expected.get(key) or 0):
            failures.append(f"{name}: expected {key}={expected.get(key)!r}, got {current.get(key)!r}.")
    _compare_range(failures, name, "duration_seconds", current, expected)
    _compare_range(failures, name, "file_size_bytes", current, expected)
    return failures


def _compare_range(
    failures: list[str],
    name: str,
    key: str,
    current: dict[str, object],
    expected: dict[str, object],
) -> None:
    value = _float_value(current.get(key))
    minimum = _float_value(expected.get(f"min_{key}"))
    maximum = _float_value(expected.get(f"max_{key}"))
    if minimum > 0 and value < minimum:
        failures.append(f"{name}: {key} {value:g} is below minimum {minimum:g}.")
    if maximum > 0 and value > maximum:
        failures.append(f"{name}: {key} {value:g} is above maximum {maximum:g}.")


def _media_stream_types(path: Path) -> set[str]:
    completed = run_ffprobe(
        [
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    data = json.loads(completed.stdout or "{}")
    streams = data.get("streams") if isinstance(data, dict) else []
    if not isinstance(streams, list):
        return set()
    return {str(stream.get("codec_type") or "") for stream in streams if isinstance(stream, dict)}


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
