from __future__ import annotations

from scripts import workflow_benchmark


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
