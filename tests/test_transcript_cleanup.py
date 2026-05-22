from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import transcript_cleanup

REGRESSION_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "transcript_cleanup_regression.json").read_text(encoding="utf-8")
)


def test_transcript_cleaner_disabled_normalizes_whitespace() -> None:
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="off"))

    assert cleaner.clean("  Xin   chào   ") == "Xin chào"
    assert cleaner.clean_many(["  A   B  ", ""]) == ["A B", ""]


def test_sanitize_removes_labels_fences_and_explanations() -> None:
    assert transcript_cleanup._sanitize_llm_output("Corrected transcript: Hello world") == "Hello world"
    assert transcript_cleanup._sanitize_llm_output("```text\nTranscript đã sửa: Xin chào\n```") == "Xin chào"
    assert transcript_cleanup._sanitize_llm_output("Giải thích: đã sửa lỗi\nXin chào") == "Xin chào"


def test_safe_cleanup_output_falls_back_for_unsafe_response() -> None:
    original = "Xin chào"
    unsafe = "Giải thích: " + ("đây là phần giải thích rất dài " * 20)

    assert transcript_cleanup._safe_cleanup_output(original, unsafe) == original


def test_cleanup_regression_fixture_covers_decision_categories() -> None:
    categories = {case["category"] for case in REGRESSION_CASES}

    assert categories == {"fix_correct", "block_wrong_edit", "keep_correct"}


@pytest.mark.parametrize("case", REGRESSION_CASES, ids=lambda case: case["id"])
def test_cleanup_regression_cases(case: dict[str, str]) -> None:
    assert transcript_cleanup._safe_cleanup_output(case["input"], case["candidate"]) == case["expected"]


def test_clean_many_uses_batch_json_response(monkeypatch) -> None:
    prompts: list[str] = []

    def fake_call(prompt: str, provider: str, config: AppConfig) -> str:
        prompts.append(prompt)
        assert provider == "ollama"
        return '["Xin chào", "Tạm biệt"]'

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", fake_call)
    cleaner = transcript_cleanup.TranscriptCleaner(
        AppConfig(transcript_cleanup_mode="light", transcript_cleanup_provider="ollama")
    )

    assert cleaner.clean_many(["xin chao", "tam biet"], "vi") == ["Xin chào", "Tạm biệt"]
    assert len(prompts) == 1
    assert "JSON array" in prompts[0]


def test_clean_many_falls_back_when_batch_shape_is_wrong(monkeypatch) -> None:
    calls: list[str] = []

    def fake_call(prompt: str, *_args) -> str:
        calls.append(prompt)
        if "JSON array" in prompt:
            return '["Chỉ một câu"]'
        if "câu một" in prompt:
            return "Câu một"
        return "Câu hai"

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", fake_call)
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="light"))

    assert cleaner.clean_many(["câu một", "câu hai"], "vi") == ["Câu một", "Câu hai"]
    assert len(calls) == 3


def test_clean_many_falls_back_to_single_cleanup_when_batch_json_is_invalid(monkeypatch) -> None:
    calls: list[str] = []

    def fake_call(prompt: str, *_args) -> str:
        calls.append(prompt)
        if "JSON array" in prompt:
            return "không phải json"
        if "OpenAI API key" in prompt:
            return "OpenAI API key không nên để trong file cấu hình"
        return "Hôm nay mình demo NLLB"

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", fake_call)
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="strong"))

    result = cleaner.clean_many(
        ["hom nay minh demo n l l b", "open ai api key khong nen de trong file cau hinh"], "vi"
    )

    assert result == [
        "Hôm nay mình demo NLLB",
        "OpenAI API key không nên để trong file cấu hình",
    ]
    assert len(calls) == 3


def test_cleanup_failure_logs_once_and_returns_original(monkeypatch, caplog) -> None:
    def raise_error(*_args):
        raise transcript_cleanup.TranscriptCleanupError("model unavailable")

    monkeypatch.setattr(transcript_cleanup, "_call_cleanup_provider", raise_error)
    cleaner = transcript_cleanup.TranscriptCleaner(AppConfig(transcript_cleanup_mode="light"))

    with caplog.at_level(logging.WARNING, logger="ai_player.services.transcript_cleanup"):
        assert cleaner.clean("xin chao", "vi") == "xin chao"
        assert cleaner.clean("tam biet", "vi") == "tam biet"

    messages = [record.message for record in caplog.records]
    assert sum("Transcript cleanup failed" in message for message in messages) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("nhẹ", "light"),
        ("mạnh", "strong"),
        ("openai-compatible", "openai"),
        ("headless-local", "local"),
    ],
)
def test_cleanup_aliases(value: str, expected: str) -> None:
    normalizer = (
        transcript_cleanup._cleanup_provider
        if "local" in value or "openai" in value
        else transcript_cleanup._cleanup_mode
    )

    assert normalizer(value) == expected


def test_local_transformers_kwargs_use_dtype_not_deprecated_torch_dtype(monkeypatch) -> None:
    monkeypatch.setattr(transcript_cleanup.importlib.util, "find_spec", lambda _name: None)
    torch = SimpleNamespace(
        float16="float16",
        float32="float32",
        cuda=SimpleNamespace(is_available=lambda: True),
    )

    kwargs = transcript_cleanup._local_transformers_load_kwargs(torch)

    assert kwargs == {"local_files_only": True, "dtype": "float16"}
    assert "torch_dtype" not in kwargs


def test_load_local_transformers_model_falls_back_for_old_transformers() -> None:
    calls: list[dict[str, object]] = []

    class FakeModelClass:
        @staticmethod
        def from_pretrained(_model_path: str, **kwargs):
            calls.append(kwargs)
            if "dtype" in kwargs:
                raise TypeError("from_pretrained() got an unexpected keyword argument 'dtype'")
            return "model"

    result = transcript_cleanup._load_local_transformers_model(
        FakeModelClass,
        "model-path",
        {"local_files_only": True, "dtype": "float32"},
    )

    assert result == "model"
    assert calls == [
        {"local_files_only": True, "dtype": "float32"},
        {"local_files_only": True, "torch_dtype": "float32"},
    ]


def test_local_transformers_input_device_avoids_meta_device(monkeypatch) -> None:
    monkeypatch.setattr(transcript_cleanup.importlib.util, "find_spec", lambda _name: None)
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    model = SimpleNamespace(device="meta", parameters=lambda: iter(()))

    assert transcript_cleanup._local_transformers_input_device(model, torch) == "cpu"
