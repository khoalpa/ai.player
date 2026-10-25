from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from ai_player.adapters.tts import vieneu_tts_server


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


def test_vieneu_tts_server_quiets_nonfatal_torchaudio_ffmpeg_probe(monkeypatch) -> None:
    levels: list[int] = []
    torio = ModuleType("torio")
    utils = ModuleType("torio.utils")
    utils.ffmpeg_utils = SimpleNamespace(set_log_level=levels.append)
    torio.utils = utils
    monkeypatch.setitem(sys.modules, "torio", torio)
    monkeypatch.setitem(sys.modules, "torio.utils", utils)
    monkeypatch.setattr(vieneu_tts_server.os, "name", "nt")

    vieneu_tts_server._quiet_torchaudio_ffmpeg_probe()

    assert levels == [8]


def test_vieneu_tts_server_ignores_missing_torchaudio_log_api(monkeypatch) -> None:
    torio = ModuleType("torio")
    utils = ModuleType("torio.utils")
    utils.ffmpeg_utils = SimpleNamespace()
    torio.utils = utils
    monkeypatch.setitem(sys.modules, "torio", torio)
    monkeypatch.setitem(sys.modules, "torio.utils", utils)
    monkeypatch.setattr(vieneu_tts_server.os, "name", "nt")

    vieneu_tts_server._quiet_torchaudio_ffmpeg_probe()
