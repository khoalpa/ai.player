from __future__ import annotations

import subprocess

from ai_player.services import capture_sources


def test_capture_duration_sanitizes_invalid_values() -> None:
    assert capture_sources._duration_seconds(float("nan")) == 1
    assert capture_sources._duration_seconds(float("inf")) == 1
    assert capture_sources._duration_seconds("bad") == 1
    assert capture_sources._duration_seconds(3.9) == 3


def test_capture_dshow_audio_sanitizes_duration(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        (tmp_path / "capture.wav").write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(capture_sources, "subprocess", subprocess)
    monkeypatch.setattr(subprocess, "run", fake_run)

    capture_sources._capture_dshow_audio(
        "Microphone",
        tmp_path / "capture.wav",
        float("nan"),
        "microphone",
    )

    assert commands[0][commands[0].index("-t") + 1] == "1"

