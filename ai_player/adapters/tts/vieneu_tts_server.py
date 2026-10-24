from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from ai_player.core.redaction import redact_secrets
from ai_player.core.value_utils import clean_message as _core_clean_message
from ai_player.core.value_utils import clean_text as _core_clean_text
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.runtime.vieneu_profile import validate_runtime_profile
from ai_player.runtime.vieneu_v3 import SDK_VERSION, engine_kwargs


def create_engine(model_name: str, device: str, backend: str):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    if importlib.metadata.version("vieneu") != SDK_VERSION:
        raise RuntimeError(f"VieNeu SDK must be {SDK_VERSION}")
    package = Path(importlib.metadata.distribution("vieneu").locate_file("vieneu"))
    validate_runtime_profile(Path(sys.prefix), package)
    if device == "auto":
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    if backend == "auto":
        backend = "pytorch" if device == "cuda" else "onnx"
    if backend == "onnx":
        device = "cpu"
    from vieneu import Vieneu

    return Vieneu(mode="v3turbo", **engine_kwargs(Path(model_name), device, backend))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["v3turbo"], default="v3turbo")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--backend", choices=["auto", "onnx", "pytorch"], default="auto")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        engine = create_engine(args.model_name, args.device, args.backend)
        _emit({"ok": True, "event": "ready", "sdk_version": SDK_VERSION, "sample_rate": engine.sample_rate})
    except Exception as exc:
        _emit({"ok": False, "error": _clean_message(exc), "trace": _clean_message(traceback.format_exc())})
        return 2
    for raw_line in sys.stdin.buffer:
        try:
            request = json.loads(raw_line.decode("utf-8"))
            if request.get("op") == "shutdown":
                engine.close()
                _emit({"ok": True, "event": "shutdown"})
                return 0
            text = _clean_text(request.get("text"))
            if not text:
                raise ValueError("Empty synthesis text")
            output = Path(str(request["output"]))
            audio = engine.infer(
                text=text,
                voice=str(request.get("voice") or "") or None,
                temperature=_float_value(request.get("temperature"), default=0.55),
                max_chars=_int_value(request.get("max_chars"), default=140, minimum=1),
            )
            import numpy as np

            if np.asarray(audio).size == 0 or not np.isfinite(audio).all():
                raise ValueError("VieNeu v3 Turbo returned invalid audio")
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(output.stem + ".partial.wav")
            try:
                engine.save(audio, str(temporary))
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
            _emit({"ok": True, "output": str(output), "sample_rate": engine.sample_rate})
        except Exception as exc:
            _emit({"ok": False, "error": _clean_message(exc), "trace": _clean_message(traceback.format_exc())})
    engine.close()
    return 0


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.buffer.write(("AI_PLAYER_JSON:" + json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _clean_message(value: object) -> str:
    return redact_secrets(_core_clean_message(value))


def _clean_text(value: object) -> str:
    return _core_clean_text(value)


def _float_value(value: object, *, default: float) -> float:
    return _core_finite_float(value, default=default)


def _int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)


if __name__ == "__main__":
    raise SystemExit(main())
