"""Exercise the actual isolated TTS server with sockets denied and an empty HF cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_player.configuration import INTERNAL_VIENEU_PYTHON, INTERNAL_VIENEU_V3_PATH, PROJECT_ROOT
from ai_player.runtime.vieneu_v3 import validate_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--source-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "output" / "vieneu-v3-verification")
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    validate_bundle(INTERNAL_VIENEU_V3_PATH, gpu=args.device == "cuda")
    manifest = json.loads((INTERNAL_VIENEU_V3_PATH / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        digest = hashlib.sha256()
        with (INTERNAL_VIENEU_V3_PATH / name).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise RuntimeError(f"Corrupt model artifact: {name}")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    texts = [
        ("Thục Đoan", "Xin chào. Đây là bản kiểm thử giọng đọc tiếng Việt chạy hoàn toàn ngoại tuyến."),
        ("Minh Triết", "Hôm nay chúng ta kiểm tra AI Player, số 123 và ngày 24 tháng 10 năm 2026."),
    ]
    requests = [
        {"op": "synthesize", "text": text, "voice": voice, "output": str(output_dir / f"{args.device}-{i}.wav")}
        for i, (voice, text) in enumerate(texts)
    ]
    requests.append({"op": "shutdown"})
    bootstrap = """import socket, runpy, os
from pathlib import Path
import ai_player
expected_root = Path(os.environ["PYTHONPATH"]).resolve()
assert Path(ai_player.__file__).resolve().is_relative_to(expected_root), ai_player.__file__
attempts = []
def denied(*args, **kwargs):
    attempts.append("socket access")
    raise RuntimeError("Network access forbidden by offline verification")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied
try:
    runpy.run_module("ai_player.adapters.tts.vieneu_tts_server", run_name="__main__")
finally:
    if attempts:
        raise RuntimeError(f"Offline engine attempted network access {len(attempts)} times")
"""
    with tempfile.TemporaryDirectory(prefix="vieneu-empty-hf-") as cache:
        env = {
            **os.environ,
            "PYTHONPATH": str(source_root),
            "AI_PLAYER_PROJECT_ROOT": str(PROJECT_ROOT),
            "PYTHONUTF8": "1",
            "HF_HOME": cache,
            "HF_HUB_CACHE": str(Path(cache) / "hub"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        started = time.monotonic()
        result = subprocess.run(
            [
                INTERNAL_VIENEU_PYTHON,
                "-X",
                "utf8",
                "-c",
                bootstrap,
                "--model-name",
                str(INTERNAL_VIENEU_V3_PATH),
                "--device",
                args.device,
                "--backend",
                "onnx" if args.device == "cpu" else "pytorch",
                "--offline",
            ],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            cwd=cache,
            timeout=600,
        )
        (output_dir / f"{args.device}-server.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        events = [
            json.loads(line.split("AI_PLAYER_JSON:", 1)[1])
            for line in result.stdout.splitlines()
            if line.startswith("AI_PLAYER_JSON:")
        ]
        if result.returncode or len(events) != 4 or not all(e.get("ok") for e in events):
            raise RuntimeError(f"Offline server failed: {events}\n{result.stderr[-4000:]}")
    import numpy as np
    import soundfile as sf

    clips = []
    for request in requests[:-1]:
        audio, rate = sf.read(request["output"])
        duration = len(audio) / rate
        if rate != 48000 or not (0.5 < duration < 60) or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 0.001:
            raise RuntimeError(f"Invalid synthesized audio: {request['output']}")
        clips.append({"voice": request["voice"], "path": request["output"], "sample_rate": rate, "seconds": duration})
    report = {
        "device": args.device,
        "source_root": str(source_root),
        "sdk_version": "3.8.3",
        "network": "socket calls denied; zero network attempts",
        "hub_cache": "empty temporary directory",
        "model_hashes_verified": True,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "clips": clips,
    }
    (output_dir / f"{args.device}-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
