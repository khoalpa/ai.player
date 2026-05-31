from __future__ import annotations

from ai_player.core.config import AppConfig
from scripts import workflow_benchmark


def test_workflow_benchmark_result_includes_stable_regression_metadata() -> None:
    result = workflow_benchmark.build_benchmark_result(
        config=AppConfig(
            performance_preset="balanced",
            whisper_model="models/asr/base",
            translator_provider="nllb_ct2",
            tts_provider="vieneu",
        ),
        audio="sample.wav",
        source_language="en",
        timings={"tts_seconds": 1.0, "translation_seconds": 0.5},
        details={"asr_segments": 2},
    )

    assert result["schema_version"] == workflow_benchmark.BENCHMARK_SCHEMA_VERSION
    assert result["preset"] == "balanced"
    assert result["audio"] == "sample.wav"
    assert result["source_language"] == "en"
    assert result["timings"] == {"translation_seconds": 0.5, "tts_seconds": 1.0}
    assert result["details"] == {"asr_segments": 2}
    assert result["config"]["translator_provider"] == "nllb_ct2"


def test_workflow_benchmark_regression_compare_reports_slow_stages() -> None:
    current = {"timings": {"asr_seconds": 1.42, "tts_seconds": 1.0}}
    baseline = {"timings": {"asr_seconds": 1.0, "tts_seconds": 1.0, "missing_seconds": 1.0}}

    regressions = workflow_benchmark.compare_timing_regressions(
        current,
        baseline,
        max_regression_percent=35.0,
    )

    assert regressions == ["asr_seconds regressed: 1.420s > 1.350s (1.000s baseline, +35.0% allowed)"]


def test_workflow_benchmark_regression_compare_accepts_small_drift() -> None:
    current = {"timings": {"asr_seconds": 1.34}}
    baseline = {"timings": {"asr_seconds": 1.0}}

    assert workflow_benchmark.compare_timing_regressions(current, baseline, max_regression_percent=35.0) == []


def test_workflow_benchmark_does_not_force_exit_for_cpu(monkeypatch) -> None:
    called = {"exit": False}
    monkeypatch.setattr(workflow_benchmark.os, "_exit", lambda _code: called.__setitem__("exit", True))

    workflow_benchmark._exit_cleanly_after_cuda_asr("cpu")

    assert not called["exit"]


def test_workflow_benchmark_forces_clean_exit_after_cuda_asr(monkeypatch) -> None:
    exit_codes: list[int] = []
    monkeypatch.setattr(workflow_benchmark.os, "_exit", exit_codes.append)

    workflow_benchmark._exit_cleanly_after_cuda_asr("cuda")

    assert exit_codes == [0]
