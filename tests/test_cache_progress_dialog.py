from __future__ import annotations

from ai_player.ui import cache_progress_dialog


def test_cache_progress_formatters_sanitize_non_finite_values() -> None:
    assert cache_progress_dialog._float_value(float("inf")) is None
    assert cache_progress_dialog._float_value(float("nan")) is None
    assert cache_progress_dialog._format_bytes(float("inf")) == "0 B"
    assert cache_progress_dialog._format_bytes(float("nan")) == "0 B"
    assert cache_progress_dialog._format_seconds(float("inf")) == "00:00"
    assert cache_progress_dialog._format_seconds(float("nan")) == "00:00"
