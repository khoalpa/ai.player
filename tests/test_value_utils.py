from __future__ import annotations

from ai_player.core import value_utils


def test_clean_message_replaces_invalid_surrogates() -> None:
    assert value_utils.clean_message("bad\udcfftext") == "bad?text"


def test_clean_text_replaces_invalid_surrogates_and_collapses_whitespace() -> None:
    assert value_utils.clean_text(" bad\udcff   text ") == "bad? text"


def test_finite_float_rejects_invalid_and_nonfinite_values() -> None:
    assert value_utils.finite_float("bad", default=0.6) == 0.6
    assert value_utils.finite_float(float("inf"), default=0.6) == 0.6
    assert value_utils.finite_float("0.4", default=0.6) == 0.4


def test_optional_number_helpers_return_none_for_invalid_values() -> None:
    assert value_utils.optional_float(float("nan")) is None
    assert value_utils.optional_float("0.4") == 0.4
    assert value_utils.optional_int(None) is None
    assert value_utils.optional_int("42") == 42


def test_nonnegative_float_sanitizes_and_clamps_negative_values() -> None:
    assert value_utils.nonnegative_float(float("inf"), default=2.0) == 2.0
    assert value_utils.nonnegative_float("-1.5", default=2.0) == 0.0


def test_clamped_float_sanitizes_nonfinite_and_bounds_values() -> None:
    assert value_utils.clamped_float(float("inf"), minimum=0.0, maximum=1.0) == 0.0
    assert value_utils.clamped_float("-1", minimum=0.0, maximum=1.0) == 0.0
    assert value_utils.clamped_float("2", minimum=0.0, maximum=1.0) == 1.0
    assert value_utils.clamped_float("0.4", minimum=0.0, maximum=1.0) == 0.4


def test_int_value_handles_invalid_values_and_minimum() -> None:
    assert value_utils.int_value("bad", default=7) == 7
    assert value_utils.int_value(0, default=7, minimum=1) == 1
    assert value_utils.int_value("42", default=7, minimum=1) == 42


def test_positive_int_clamps_to_one_after_defaulting_invalid_values() -> None:
    assert value_utils.positive_int("bad", default=7) == 7
    assert value_utils.positive_int(0, default=7) == 1
