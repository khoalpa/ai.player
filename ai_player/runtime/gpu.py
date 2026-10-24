from __future__ import annotations

import os
import shutil
import site
import sys
from pathlib import Path

_CUDA_DLL_PATHS_CONFIGURED = False
_DLL_DIRECTORY_HANDLES: list[object] = []


def configure_cuda_dll_paths() -> None:
    global _CUDA_DLL_PATHS_CONFIGURED
    if _CUDA_DLL_PATHS_CONFIGURED:
        return
    _CUDA_DLL_PATHS_CONFIGURED = True
    if os.name != "nt":
        return

    candidates: list[Path] = []
    for root in _site_package_roots():
        candidates.extend(
            [
                root / "nvidia" / "cublas" / "bin",
                root / "nvidia" / "cudnn" / "bin",
                root / "nvidia" / "cuda_nvrtc" / "bin",
                root / "ctranslate2",
                root / "torch" / "lib",
            ]
        )

    existing = [path for path in candidates if path.exists()]
    if not existing:
        return

    current_path = os.environ.get("PATH", "")
    current_parts = {part.casefold() for part in current_path.split(os.pathsep) if part}
    prepend = []
    for path in existing:
        path_text = str(path)
        if path_text.casefold() not in current_parts:
            prepend.append(path_text)
        if hasattr(os, "add_dll_directory"):
            try:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(path_text))
            except OSError:
                pass
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + [current_path])


def ctranslate2_cuda_available() -> bool:
    configure_cuda_dll_paths()
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def torch_cuda_available() -> bool:
    configure_cuda_dll_paths()
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def onnx_cuda_available() -> bool:
    configure_cuda_dll_paths()
    try:
        import onnxruntime as ort

        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def cuda_runtime_files_available(*roots: Path) -> bool:
    configure_cuda_dll_paths()
    if shutil.which("cublas64_12.dll"):
        return True
    return any(root.exists() and any(root.rglob("cublas64_12.dll")) for root in roots)


def _site_package_roots() -> list[Path]:
    roots = []
    for value in site.getsitepackages() + [site.getusersitepackages()]:
        if value:
            roots.append(Path(value))
    roots.append(Path(sys.prefix) / "Lib" / "site-packages")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique
