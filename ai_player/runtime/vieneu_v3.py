"""The single supported VieNeu release and its offline bundle layout."""

from __future__ import annotations

import json
from pathlib import Path

SDK_VERSION = "3.8.3"
MODEL_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
MODEL_REVISION = "61b85e3d937fbbacb387714180e8182823512523"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
CODEC_REVISION = "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"
GPU_CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano"
GPU_CODEC_REVISION = "6aa02b01e445cc585582cf0ba480bc3ea6c8dd68"
GRAPH_FILES = (
    "config.json",
    "tokenizer.json",
    "vieneu_prefill.onnx",
    "vieneu_decode_step.onnx",
    "vieneu_acoustic_cached.onnx",
    "vieneu_backbone_shared.data",
    "vieneu_v3_heads.npz",
)
CODEC_FILES = (
    "moss_audio_tokenizer_decode_full.onnx",
    "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx",
    "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx",
    "moss_audio_tokenizer_encode.data",
)
CPU_FILES = (
    "manifest.json",
    "model/voices_v3_turbo.json",
    "model/config.json",
    "model/denoiser.onnx",
    "model/speaker_encoder.onnx",
    *(f"model/onnx_update/{name}" for name in GRAPH_FILES),
    *(f"codec/{name}" for name in CODEC_FILES),
)
GPU_FILES = (
    "model/update/config.json",
    "model/update/model.safetensors",
    "model/update/tokenizer.json",
    "model/update/tokenizer_config.json",
    "model/update/special_tokens_map.json",
    "codec-pytorch/config.json",
    "codec-pytorch/model-00001-of-00001.safetensors",
    "codec-pytorch/model.safetensors.index.json",
    "codec-pytorch/configuration_moss_audio_tokenizer.py",
    "codec-pytorch/modeling_moss_audio_tokenizer.py",
    "codec-pytorch/__init__.py",
)


def validate_bundle(root: Path, *, gpu: bool = False) -> None:
    """Fail before engine startup; never interpret a legacy model as v3."""
    required = CPU_FILES + (GPU_FILES if gpu else ())
    missing = [name for name in required if not (root / name).is_file() or (root / name).stat().st_size == 0]
    if missing:
        raise ValueError(
            "Thiếu mô hình VieNeu v3 Turbo. Chạy scripts/download_vieneu_tts_models.ps1: " + ", ".join(missing)
        )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("sdk_version"), manifest.get("model_revision"), manifest.get("codec_revision")) != (
        SDK_VERSION,
        MODEL_REVISION,
        CODEC_REVISION,
    ):
        raise ValueError("Bộ mô hình VieNeu v3 Turbo không khớp phiên bản đã kiểm thử.")
    if gpu and manifest.get("gpu_codec_revision") != GPU_CODEC_REVISION:
        raise ValueError("Codec GPU VieNeu v3 Turbo không khớp phiên bản đã kiểm thử.")


def engine_kwargs(root: Path, device: str, backend: str) -> dict:
    validate_bundle(root, gpu=backend == "pytorch")
    return {
        "backbone_repo": str(root / "model"),
        "onnx_dir": str(root / "model" / "onnx_update"),
        "codec_dir": str(root / "codec"),
        "moss_tokenizer": str(root / "codec-pytorch"),
        "device": device,
        "backend": backend,
        "precision": "fp32",
    }
