from __future__ import annotations

from pathlib import Path

from ai_player.runtime.runtime_diagnostics import DiagnosticItem, DiagnosticSection, RuntimeDiagnostics
from ai_player.ui import runtime_doctor_onboarding


def test_runtime_doctor_profile_summary_reports_lite_offline_and_gpu(monkeypatch) -> None:
    def fake_collect(*, include_audio_devices: bool, profile: str) -> RuntimeDiagnostics:
        assert include_audio_devices is False
        if profile == "lite":
            items = (DiagnosticItem("PySide6", "OK", "", required=True),)
        else:
            items = (
                DiagnosticItem("faster_whisper", "OK", "", required=True),
                DiagnosticItem("Whisper", "WARN", "missing model"),
            )
        return RuntimeDiagnostics(
            python="python",
            project_root=Path("."),
            sections=(DiagnosticSection("Demo", items),),
        )

    monkeypatch.setattr(runtime_doctor_onboarding, "collect_runtime_diagnostics", fake_collect)
    monkeypatch.setattr(runtime_doctor_onboarding.shutil, "which", lambda _name: None)

    summary = runtime_doctor_onboarding.build_runtime_doctor_profile_summary()

    assert "Lite: ready" in summary
    assert "Offline AI: usable, but 1 optional/model item(s) need attention" in summary
    assert "GPU: optional, no NVIDIA runtime detected" in summary
