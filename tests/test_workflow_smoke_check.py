from __future__ import annotations

from scripts import workflow_smoke_check


def test_workflow_smoke_baseline_loads_and_checks_current_samples() -> None:
    baseline = workflow_smoke_check.load_smoke_baseline()
    metrics = workflow_smoke_check.collect_smoke_metrics()

    assert workflow_smoke_check.compare_smoke_metrics(metrics, baseline) == []
    assert metrics["samples"]["demo_video"]["has_audio_stream"] is True
    assert metrics["samples"]["demo_video"]["has_video_stream"] is True
    assert metrics["samples"]["demo_transcript"]["segment_count"] == 2


def test_workflow_smoke_compare_reports_media_regressions() -> None:
    metrics = {
        "samples": {
            "demo_video": {
                "exists": True,
                "duration_seconds": 0.25,
                "file_size_bytes": 10,
                "has_audio_stream": False,
                "has_video_stream": True,
            }
        }
    }
    baseline = {
        "schema_version": workflow_smoke_check.SMOKE_SCHEMA_VERSION,
        "samples": {
            "demo_video": {
                "min_duration_seconds": 1.0,
                "min_file_size_bytes": 100,
                "has_audio_stream": True,
                "has_video_stream": True,
            }
        },
    }

    failures = workflow_smoke_check.compare_smoke_metrics(metrics, baseline)

    assert "demo_video: expected has_audio_stream=True, got False." in failures
    assert "demo_video: duration_seconds 0.25 is below minimum 1." in failures
    assert "demo_video: file_size_bytes 10 is below minimum 100." in failures


def test_workflow_smoke_counts_srt_segments() -> None:
    assert workflow_smoke_check.count_srt_segments("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n") == 1
    assert workflow_smoke_check.count_srt_segments("No timestamps here") == 0
