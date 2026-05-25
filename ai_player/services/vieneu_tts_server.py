from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from ai_player.core.value_utils import clean_message as _core_clean_message
from ai_player.core.value_utils import clean_text as _core_clean_text
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import int_value as _core_int_value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--api-base", default="")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--decoder-path", default="")
    parser.add_argument("--encoder-path", default="")
    parser.add_argument("--standard-codec-path", default="")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"

    root = Path(args.root)
    import_root = root / "src" if (root / "src" / "vieneu").exists() else root
    if import_root.exists():
        sys.path.insert(0, str(import_root))

    try:
        from vieneu import Vieneu

        kwargs = _engine_kwargs(
            mode=args.mode,
            api_base=args.api_base,
            model_name=args.model_name,
            device=args.device,
            backend=args.backend,
            decoder_path=args.decoder_path,
            encoder_path=args.encoder_path,
            standard_codec_path=args.standard_codec_path,
        )
        engine = Vieneu(mode=args.mode, **kwargs)
        _emit({"ok": True, "event": "ready"})
    except Exception as exc:
        _emit(
            {
                "ok": False,
                "error": _clean_message(f"VieNeu init failed: {exc}"),
                "trace": _clean_message(traceback.format_exc()),
            }
        )
        return 2

    stdin = sys.stdin.buffer
    for raw_line in stdin:
        try:
            line = raw_line.decode("utf-8", errors="replace")
            request = json.loads(line)
            if request.get("op") == "shutdown":
                _emit({"ok": True, "event": "shutdown"})
                return 0

            text = _clean_text(request.get("text"))
            output = Path(str(request.get("output") or ""))
            voice_id = str(request.get("voice") or "").strip()
            temperature = _float_value(request.get("temperature"), default=0.6)
            max_chars = _int_value(request.get("max_chars"), default=160, minimum=1)

            voice = engine.get_preset_voice(voice_id) if voice_id else None
            audio = engine.infer(
                text=text,
                voice=voice,
                temperature=temperature,
                max_chars=max_chars,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            engine.save(audio, str(output))
            _emit({"ok": True, "output": str(output)})
        except Exception as exc:
            _emit({"ok": False, "error": _clean_message(exc), "trace": _clean_message(traceback.format_exc())})

    return 0


def _engine_kwargs(
    *,
    mode: str,
    api_base: str,
    model_name: str,
    device: str,
    backend: str,
    decoder_path: str,
    encoder_path: str,
    standard_codec_path: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if mode == "remote":
        if api_base:
            kwargs["api_base"] = api_base
        if model_name:
            kwargs["model_name"] = model_name
        return kwargs

    runtime_device = "cuda" if device == "cuda" else "cpu"
    if model_name:
        kwargs["backbone_repo"] = _resolve_local_gguf_if_dir(model_name)
    if mode == "standard":
        kwargs["backbone_device"] = runtime_device
        kwargs["codec_device"] = runtime_device
        if standard_codec_path:
            kwargs["codec_repo"] = _resolve_existing_dir(standard_codec_path)
    else:
        if decoder_path:
            kwargs["decoder_repo"] = _resolve_existing_file(decoder_path)
        if encoder_path:
            kwargs["encoder_repo"] = _resolve_existing_file(encoder_path)
        kwargs["device"] = runtime_device
        if mode in {"fast", "turbo_gpu"} and backend:
            kwargs["backend"] = backend
    return kwargs


def _resolve_local_gguf_if_dir(model_name: str) -> str:
    path = Path(model_name)
    if not path.exists() or not path.is_dir():
        return model_name
    candidates = sorted(
        [item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".gguf"],
        key=lambda item: item.name.lower(),
    )
    return str(candidates[0].resolve()) if candidates else model_name


def _resolve_existing_file(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_file() else value


def _resolve_existing_dir(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_dir() else value


def _emit(payload: dict[str, Any]) -> None:
    line = "AI_PLAYER_JSON:" + json.dumps(payload, ensure_ascii=True) + "\n"
    sys.stdout.buffer.write(line.encode("utf-8", errors="surrogatepass"))
    sys.stdout.buffer.flush()


def _clean_message(value: object) -> str:
    return _core_clean_message(value)


def _clean_text(value: object) -> str:
    return _core_clean_text(value)


def _float_value(value: object, *, default: float) -> float:
    return _core_finite_float(value, default=default)


def _int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)


if __name__ == "__main__":
    raise SystemExit(main())
