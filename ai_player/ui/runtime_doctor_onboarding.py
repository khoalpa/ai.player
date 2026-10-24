from __future__ import annotations

import shutil

from ai_player.runtime.runtime_diagnostics import RuntimeDiagnostics, collect_runtime_diagnostics


def build_runtime_doctor_profile_summary() -> str:
    lines = [
        _diagnostic_profile_line("Lite", collect_runtime_diagnostics(include_audio_devices=False, profile="lite")),
        _diagnostic_profile_line(
            "Offline AI",
            collect_runtime_diagnostics(include_audio_devices=False, profile="offline-ai"),
            include_warnings=True,
        ),
        _gpu_profile_line(),
    ]
    return "\n".join(lines)


def _diagnostic_profile_line(name: str, report: RuntimeDiagnostics, *, include_warnings: bool = False) -> str:
    required_missing = sum(
        1 for section in report.sections for item in section.items if item.required and item.status == "MISS"
    )
    warnings = sum(1 for section in report.sections for item in section.items if item.status == "WARN")
    if required_missing:
        return f"{name}: needs attention ({required_missing} required missing)"
    if include_warnings and warnings:
        return f"{name}: usable, but {warnings} optional/model item(s) need attention"
    return f"{name}: ready"


def _gpu_profile_line() -> str:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return "GPU: optional, no NVIDIA runtime detected"

    checks = []
    try:
        import torch

        checks.append(f"Torch CUDA={torch.cuda.is_available()}")
    except Exception as exc:
        checks.append(f"Torch check failed: {exc}")
    try:
        import ctranslate2

        checks.append(f"CTranslate2 CUDA devices={ctranslate2.get_cuda_device_count()}")
    except Exception as exc:
        checks.append(f"CTranslate2 check failed: {exc}")
    detail = "; ".join(checks) if checks else f"nvidia-smi: {nvidia_smi}"
    return f"GPU: {detail}"
