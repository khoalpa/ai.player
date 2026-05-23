from __future__ import annotations

from ai_player.services import vieneu_tts_server


def test_vieneu_tts_server_float_value_rejects_non_finite_values() -> None:
    assert vieneu_tts_server._float_value(float("nan"), default=0.6) == 0.6
    assert vieneu_tts_server._float_value(float("inf"), default=0.6) == 0.6
    assert vieneu_tts_server._float_value("bad", default=0.6) == 0.6
    assert vieneu_tts_server._float_value("0.4", default=0.6) == 0.4


def test_vieneu_tts_server_int_value_clamps_invalid_values() -> None:
    assert vieneu_tts_server._int_value(float("inf"), default=160, minimum=1) == 160
    assert vieneu_tts_server._int_value("bad", default=160, minimum=1) == 160
    assert vieneu_tts_server._int_value(0, default=160, minimum=1) == 1
    assert vieneu_tts_server._int_value("42", default=160, minimum=1) == 42
