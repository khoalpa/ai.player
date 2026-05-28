from __future__ import annotations

import sys

import pytest

from ai_player.core.secret_store import protect_text, reveal_text


def test_reveal_text_ignores_missing_payload() -> None:
    assert reveal_text(None) == ""
    assert reveal_text({}) == ""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI is only available on Windows")
def test_protect_text_round_trips_with_windows_dpapi() -> None:
    payload = protect_text("hash-secret")

    assert payload["scheme"] == "win32-dpapi"
    assert payload["value"]
    assert "hash-secret" not in str(payload)
    assert reveal_text(payload) == "hash-secret"
