from __future__ import annotations

import sys

import pytest

from ai_player.core import gpu, offline_env, optional_imports
from ai_player.core.config import AppConfig
from ai_player.services import runtime_warmup


def test_offline_environment_sets_and_restores(monkeypatch) -> None:
    for name in offline_env.HF_OFFLINE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    token = offline_env.push_hf_offline_environment(True)
    assert {name: offline_env.os.environ.get(name) for name in offline_env.HF_OFFLINE_ENV_VARS} == {
        name: "1" for name in offline_env.HF_OFFLINE_ENV_VARS
    }

    offline_env.pop_hf_offline_environment(token)
    assert all(name not in offline_env.os.environ for name in offline_env.HF_OFFLINE_ENV_VARS)


def test_offline_environment_nested_pop_keeps_inner_state(monkeypatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "previous")
    outer = offline_env.push_hf_offline_environment(True)
    inner = offline_env.push_hf_offline_environment(True)

    offline_env.pop_hf_offline_environment(inner)
    assert offline_env.os.environ["HF_HUB_OFFLINE"] == "1"

    offline_env.pop_hf_offline_environment(outer)
    assert offline_env.os.environ["HF_HUB_OFFLINE"] == "previous"


@pytest.mark.parametrize("module_name", optional_imports.UNNEEDED_TRANSFORMERS_OPTIONAL_IMPORTS[:2])
def test_optional_import_block_restores_previous_modules(monkeypatch, module_name: str) -> None:
    sentinel = object()
    monkeypatch.setitem(sys.modules, module_name, sentinel)

    with optional_imports.block_unneeded_transformers_optional_imports():
        assert sys.modules[module_name] is None

    assert sys.modules[module_name] is sentinel


def test_install_optional_import_blocks_only_sets_missing(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setitem(sys.modules, "sklearn", sentinel)
    monkeypatch.delitem(sys.modules, "pandas", raising=False)

    optional_imports.install_unneeded_transformers_optional_import_blocks()

    assert sys.modules["sklearn"] is sentinel
    assert sys.modules["pandas"] is None


def test_push_offline_environment_disabled_token_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    token = offline_env.push_hf_offline_environment(False)
    offline_env.pop_hf_offline_environment(token)

    assert "TRANSFORMERS_OFFLINE" not in offline_env.os.environ


def test_warm_runtime_components_reports_progress_when_dependencies_are_stubbed(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(runtime_warmup, "_warm_whisper", lambda _config: None)

    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=True,
        runtime_warmup_translation=False,
        runtime_warmup_tts=False,
    )
    timings = runtime_warmup.warm_runtime_components(config, progress_callback=calls.append)

    assert "whisper_load_seconds" in timings
    assert calls


def test_warm_runtime_components_warms_transcript_cleanup(monkeypatch) -> None:
    calls: list[str] = []

    class FakeCleaner:
        def __init__(self, _config: AppConfig) -> None:
            pass

        def clean(self, text: str, source_language: str | None = None) -> str:
            calls.append(text)
            return text

    monkeypatch.setattr(runtime_warmup, "TranscriptCleaner", FakeCleaner)
    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=False,
        runtime_warmup_translation=False,
        runtime_warmup_tts=False,
        transcript_cleanup_mode="light",
    )

    timings = runtime_warmup.warm_runtime_components(config)

    assert "transcript_cleanup_seconds" in timings
    assert calls


def test_runtime_warmup_stage_detection_skips_empty_configuration() -> None:
    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=False,
        runtime_warmup_translation=True,
        translator_provider="none",
        runtime_warmup_tts=False,
        transcript_cleanup_mode="off",
    )

    assert runtime_warmup.has_runtime_warmup_stage(config) is False


def test_runtime_warmup_stage_detection_keeps_tts_default_off() -> None:
    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=False,
        runtime_warmup_translation=False,
        transcript_cleanup_mode="off",
        tts_provider="vieneu",
    )

    assert runtime_warmup.has_runtime_warmup_stage(config) is False


def test_warm_runtime_components_keeps_tts_default_off(monkeypatch) -> None:
    monkeypatch.setattr(runtime_warmup, "_warm_tts", lambda _config: pytest.fail("TTS should not warm by default"))
    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=False,
        runtime_warmup_translation=False,
        transcript_cleanup_mode="off",
        tts_provider="vieneu",
    )

    assert runtime_warmup.warm_runtime_components(config) == {}


def test_runtime_warmup_stage_detection_includes_cleanup() -> None:
    config = AppConfig(
        runtime_warmup_enabled=True,
        runtime_warmup_whisper=False,
        runtime_warmup_translation=False,
        runtime_warmup_tts=False,
        transcript_cleanup_mode="light",
    )

    assert runtime_warmup.has_runtime_warmup_stage(config) is True


def test_cuda_runtime_files_available_finds_nested_dll(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gpu, "configure_cuda_dll_paths", lambda: None)
    monkeypatch.setattr(gpu.shutil, "which", lambda _name: None)
    dll = tmp_path / "pkg" / "bin" / "cublas64_12.dll"
    dll.parent.mkdir(parents=True)
    dll.write_text("", encoding="utf-8")

    assert gpu.cuda_runtime_files_available(tmp_path)
