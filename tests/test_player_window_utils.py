from __future__ import annotations

from ai_player.core.config import AppConfig
from ai_player.ui import player_window_utils as utils


def test_repair_mojibake_repairs_common_vietnamese_text() -> None:
    assert utils.repair_mojibake("KhÃ´ng") == "Không"


def test_html_with_breaks_escapes_and_preserves_lines() -> None:
    assert utils.html_with_breaks("<a>\nb") == "&lt;a&gt;<br>b"


def test_format_bitrate_for_mbps() -> None:
    assert utils.format_bitrate(2_500_000) == "2.50 Mbps"


def test_format_rate_fraction() -> None:
    assert utils.format_rate("30000/1001") == "29.97"


def test_safe_native_dubbing_config_forces_cpu_when_cuda_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AI_PLAYER_DISABLE_CUDA", "1")
    config = AppConfig(local_translation_device="cuda", whisper_device="cuda", vieneu_tts_device="cuda")

    safe = utils.safe_native_dubbing_config(config)

    assert safe.local_translation_device == "cpu"
    assert safe.whisper_compute_type == "int8"


def test_safe_native_dubbing_config_keeps_cuda_when_runtime_is_ready(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_DISABLE_CUDA", raising=False)
    monkeypatch.setattr(utils, "_cuda_runtime_ready", lambda: True)
    config = AppConfig(local_translation_device="cuda", whisper_device="cuda", vieneu_tts_device="cuda")

    assert utils.safe_native_dubbing_config(config) == config
