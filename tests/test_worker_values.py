from __future__ import annotations

from ai_player.core.config import AppConfig
from ai_player.workers import worker_values


def test_clean_worker_text_decodes_bytes_and_collapses_space() -> None:
    assert worker_values.clean_worker_text(b" hello   world ") == "hello world"


def test_clean_message_replaces_invalid_surrogates() -> None:
    assert worker_values.clean_message("bad\udcfftext") == "bad?text"


def test_json_text_decodes_bytes_collapses_space_and_uses_default() -> None:
    assert worker_values.json_text(b" hello   world ", default="fallback") == "hello world"
    assert worker_values.json_text("   ", default=None) is None


def test_align_text_results_uses_fallback_for_invalid_short_or_blank_items() -> None:
    assert worker_values.align_text_results(["one", "two"], "not a list") == ["one", "two"]
    assert worker_values.align_text_results(["one", "two", "three"], [{"text": "mot"}, b"hai", ""]) == [
        "one",
        "hai",
        "three",
    ]


def test_clean_language_normalizes_blank_and_case() -> None:
    assert worker_values.clean_language(b" EN ") == "en"
    assert worker_values.clean_language("   ") is None


def test_selected_source_language_treats_auto_and_blank_as_none() -> None:
    assert worker_values.selected_source_language(AppConfig(source_language="auto")) is None
    assert worker_values.selected_source_language(AppConfig(source_language="   ")) is None
    assert worker_values.selected_source_language(AppConfig(source_language=" EN ")) == "en"


def test_tts_disabled_uses_normalized_provider() -> None:
    assert worker_values.tts_disabled(AppConfig(tts_provider="none"))
    assert worker_values.tts_disabled(AppConfig(tts_provider="off"))
    assert not worker_values.tts_disabled(AppConfig(tts_provider="edge"))


def test_voice_tts_suffix_matches_existing_worker_convention() -> None:
    assert worker_values.voice_tts_suffix(AppConfig(tts_provider="vieneu")) == "wav"
    assert worker_values.voice_tts_suffix(AppConfig(tts_provider="edge")) == "mp3"
    assert worker_values.voice_tts_suffix(AppConfig(tts_provider="none")) == "mp3"


def test_finite_seconds_preserves_negative_values_but_sanitizes_nonfinite() -> None:
    assert worker_values.finite_seconds("-1.5", 0.0) == -1.5
    assert worker_values.finite_seconds(float("inf"), 3.0) == 3.0


def test_duration_value_sanitizes_nonfinite_and_applies_minimum() -> None:
    assert worker_values.duration_value(float("inf"), default=2.0) == 2.0
    assert worker_values.duration_value("-1.5", default=2.0, minimum=0.5) == 0.5


def test_json_number_rejects_nonfinite_values() -> None:
    assert worker_values.json_number("1e9999", default=None) is None
    assert worker_values.json_number("1.25", default=None) == 1.25


def test_nonnegative_finite_seconds_clamps_negative_values() -> None:
    assert worker_values.nonnegative_finite_seconds("-1.5", 0.0) == 0.0
    assert worker_values.nonnegative_finite_seconds(float("nan"), 3.0) == 3.0


def test_format_hhmmss_supports_truncate_and_rounding_modes() -> None:
    assert worker_values.format_hhmmss(3661.8) == "01:01:01"
    assert worker_values.format_hhmmss(3661.8, round_seconds=True) == "01:01:02"
    assert worker_values.format_hhmmss(float("inf")) == "00:00:00"


def test_int_helpers_clamp_invalid_values() -> None:
    assert worker_values.int_value("bad", default=7) == 7
    assert worker_values.positive_int(0, default=7) == 1
    assert worker_values.clamped_int(99, default=7, minimum=1, maximum=10) == 10


def test_segment_start_key_sanitizes_nonfinite_values() -> None:
    assert worker_values.segment_start_key(1.2345) == 1234
    assert worker_values.segment_start_key(float("inf")) == 0
