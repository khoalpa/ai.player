"""Download only the pinned v3 Turbo artifacts; write readiness last."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_player.configuration import INTERNAL_VIENEU_V3_PATH
from ai_player.runtime.vieneu_v3 import (
    CODEC_FILES,
    CODEC_REPO,
    CODEC_REVISION,
    CPU_FILES,
    GPU_CODEC_REPO,
    GPU_CODEC_REVISION,
    GPU_FILES,
    MODEL_REPO,
    MODEL_REVISION,
    SDK_VERSION,
    validate_bundle,
)


def main() -> None:
    os.environ.update(HF_HUB_OFFLINE="0", TRANSFORMERS_OFFLINE="0")
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()
    root = INTERNAL_VIENEU_V3_PATH
    root.mkdir(parents=True, exist_ok=True)
    patterns = ["config.json", "onnx_update/*", "denoiser.onnx", "speaker_encoder.onnx"]
    if args.cuda:
        patterns.append("update/*")
    snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=root / "model", allow_patterns=patterns)
    snapshot_download(CODEC_REPO, revision=CODEC_REVISION, local_dir=root / "codec", allow_patterns=list(CODEC_FILES))
    if args.cuda:
        snapshot_download(
            GPU_CODEC_REPO,
            revision=GPU_CODEC_REVISION,
            local_dir=root / "codec-pytorch",
            allow_patterns=["*.json", "*.py", "*.safetensors"],
        )
    package = importlib.metadata.distribution("vieneu")
    if package.version != SDK_VERSION:
        raise RuntimeError("Unexpected VieNeu SDK version")
    shutil.copyfile(package.locate_file("vieneu/assets/voices_v3_turbo.json"), root / "model/voices_v3_turbo.json")
    files = [name for name in CPU_FILES + (GPU_FILES if args.cuda else ()) if name != "manifest.json"]
    hashes = {}
    for name in files:
        digest = hashlib.sha256()
        with (root / name).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        hashes[name] = digest.hexdigest()
    manifest = {
        "sdk_version": SDK_VERSION,
        "model_revision": MODEL_REVISION,
        "codec_revision": CODEC_REVISION,
        "gpu_codec_revision": GPU_CODEC_REVISION if args.cuda else None,
        "sha256": hashes,
    }
    temporary = root / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(root / "manifest.json")
    validate_bundle(root, gpu=args.cuda)
    print(f"VieNeu v3 Turbo offline bundle ready: {root}")


if __name__ == "__main__":
    main()
