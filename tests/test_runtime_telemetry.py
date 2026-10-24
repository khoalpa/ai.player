from __future__ import annotations

from ai_player.runtime.runtime_telemetry import RuntimeTelemetry, format_runtime_telemetry


def test_runtime_telemetry_collects_counters_and_p95_stage_latency() -> None:
    telemetry = RuntimeTelemetry(sample_limit=4)
    telemetry.increment("dubbing.buffer_underrun")
    telemetry.increment("dubbing.buffer_underrun", 2)
    for elapsed in (10, 20, 30, 40, 50):
        telemetry.observe_stage("dubbing", "translate", elapsed)

    snapshot = telemetry.snapshot()

    assert snapshot.counters == {"dubbing.buffer_underrun": 3}
    assert snapshot.stage_p95_ms == {"dubbing.translate": 50.0}


def test_runtime_telemetry_ignores_invalid_stage_samples_and_can_reset() -> None:
    telemetry = RuntimeTelemetry()
    telemetry.observe_stage("dubbing", "tts", float("nan"))
    telemetry.increment("dubbing.segment_fallback")
    telemetry.reset()

    assert telemetry.snapshot().counters == {}
    assert telemetry.snapshot().stage_p95_ms == {}


def test_runtime_telemetry_formats_localized_compact_summary() -> None:
    telemetry = RuntimeTelemetry()
    telemetry.increment("dubbing.buffer_underrun", 2)
    telemetry.increment("dubbing.tts_fallback")
    telemetry.observe_stage("dubbing", "translate", 120)

    assert "khựng 2" in format_runtime_telemetry(telemetry.snapshot(), "vi")
    assert "fallbacks 1" in format_runtime_telemetry(telemetry.snapshot(), "en")
