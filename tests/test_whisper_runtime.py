from __future__ import annotations

import pytest

from ai_player.services import whisper_runtime


@pytest.mark.parametrize(
    ("compute", "device", "expected"),
    [("float16", "cpu", "int8"), ("float32", "cpu", "int8"), ("int8", "cuda", "int8")],
)
def test_effective_whisper_compute_type(compute: str, device: str, expected: str) -> None:
    assert whisper_runtime.effective_whisper_compute_type(compute, device) == expected


@pytest.mark.parametrize("cuda_available", [False, True])
def test_effective_whisper_device_auto_uses_cuda_probe(monkeypatch, cuda_available: bool) -> None:
    monkeypatch.setattr(whisper_runtime, "_cuda_runtime_available", lambda: cuda_available)

    assert whisper_runtime.effective_whisper_device("auto") == ("cuda" if cuda_available else "cpu")


def test_shared_whisper_model_materializes_segments() -> None:
    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return (item for item in [1, 2]), "info"

    shared = whisper_runtime.SharedWhisperModel(
        FakeModel(),
        whisper_runtime.WhisperRuntimeKey("m", "cpu", "int8", True),
    )

    assert shared.transcribe("audio") == ([1, 2], "info")


def test_shared_whisper_model_cache_reuses_key(monkeypatch) -> None:
    whisper_runtime.clear_shared_whisper_models()
    monkeypatch.setattr(whisper_runtime, "_create_whisper_model", lambda *_args, **_kwargs: object())

    first = whisper_runtime.get_shared_whisper_model("model", device="cpu", compute_type="int8", local_files_only=True)
    second = whisper_runtime.get_shared_whisper_model("model", device="cpu", compute_type="int8", local_files_only=True)

    assert second is first


def test_normalize_model_path_resolves_existing_path(tmp_path) -> None:
    assert whisper_runtime._normalize_model_path(str(tmp_path)) == str(tmp_path.resolve())
