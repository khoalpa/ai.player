from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ai_player.adapters.tts import tts_vieneu
from ai_player.adapters.tts.tts_base import TTSError, _tts_cache_path
from ai_player.configuration import AppConfig
from ai_player.runtime.vieneu_v3 import (
    CODEC_REVISION,
    CPU_FILES,
    MODEL_REVISION,
    SDK_VERSION,
    engine_kwargs,
    validate_bundle,
)


def _bundle(root):
    for name in CPU_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"model")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "sdk_version": SDK_VERSION,
                "model_revision": MODEL_REVISION,
                "codec_revision": CODEC_REVISION,
            }
        )
    )


@pytest.mark.parametrize("mode", ["standard", "turbo", "fast", "remote", "xpu", "turbo_gpu", "v3nano"])
def test_removed_engines_cannot_be_selected(mode):
    with pytest.raises(TTSError, match="v3"):
        tts_vieneu.VieNeuTTSProvider(AppConfig(vieneu_tts_mode=mode)).synthesize("Xin chào", None)


def test_missing_codec_fails_before_engine_start_even_when_offline_flag_false(tmp_path):
    _bundle(tmp_path)
    (tmp_path / "codec/moss_audio_tokenizer_decode_shared.data").unlink()
    config = AppConfig(vieneu_tts_offline=False)
    with pytest.raises(TTSError, match="decode_shared"):
        tts_vieneu._validate_vieneu_local_files(config, "v3turbo", str(tmp_path))


def test_mismatched_bundle_revision_rejected(tmp_path):
    _bundle(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"sdk_version": "2.0"}))
    with pytest.raises(ValueError, match="phiên bản"):
        validate_bundle(tmp_path)


def test_cpu_bundle_uses_only_explicit_local_paths(tmp_path):
    _bundle(tmp_path)
    kwargs = engine_kwargs(tmp_path, "cpu", "onnx")
    assert kwargs["backbone_repo"] == str(tmp_path / "model")
    assert kwargs["codec_dir"] == str(tmp_path / "codec")
    assert kwargs["onnx_dir"] == str(tmp_path / "model/onnx_update")
    with pytest.raises(ValueError, match="model.safetensors"):
        engine_kwargs(tmp_path, "cuda", "pytorch")


def test_failed_gpu_retries_cpu_with_same_v3_bundle(monkeypatch, tmp_path):
    config = AppConfig(vieneu_tts_device="cuda", vieneu_tts_backend="pytorch")
    provider = tts_vieneu.VieNeuTTSProvider(config)
    attempts = []

    def synthesize(candidate, text, output, voice):
        attempts.append(candidate)
        if candidate.vieneu_tts_device == "cuda":
            raise RuntimeError("CUDA out of memory")
        output.write_bytes(b"audio")

    monkeypatch.setattr(provider, "_synthesize_with_config", synthesize)
    provider.synthesize("Xin chào", tmp_path / "out.wav")
    assert [(c.vieneu_tts_mode, c.vieneu_tts_device, c.vieneu_tts_backend) for c in attempts] == [
        ("v3turbo", "cuda", "pytorch"),
        ("v3turbo", "cpu", "onnx"),
    ]
    assert all(c.vieneu_tts_model_name == config.vieneu_tts_model_name for c in attempts)


def test_missing_runtime_never_imports_host_engine(monkeypatch, tmp_path):
    _bundle(tmp_path)
    config = AppConfig(vieneu_tts_python=str(tmp_path / "absent.exe"), vieneu_tts_model_name=str(tmp_path))
    monkeypatch.setattr(tts_vieneu, "_get_vieneu_engine", lambda _: pytest.fail("Must not use host environment"))
    with pytest.raises(TTSError, match="setup_vieneu_runtime"):
        tts_vieneu.VieNeuTTSProvider(config).synthesize("Xin chào", tmp_path / "out.wav")


def test_v3_voice_catalog_and_cache_are_separate_from_old_audio(tmp_path):
    config = AppConfig()
    voices = tts_vieneu.vieneu_voices(None)
    assert len(voices) == 25
    assert {config.tts_voice, config.tts_male_voice, config.tts_female_voice} <= {v.id for v in voices}
    assert "Doan" not in {v.id for v in voices}
    assert _tts_cache_path("vieneu", config, "Xin chào", config.tts_voice, tmp_path / "out.wav") != _tts_cache_path(
        "vieneu", replace(config, vieneu_tts_mode="standard"), "Xin chào", config.tts_voice, tmp_path / "out.wav"
    )
