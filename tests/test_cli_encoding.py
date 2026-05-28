from __future__ import annotations

from ai_player.core.cli_encoding import prefer_utf8_stdio


class FakeStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_prefer_utf8_stdio_reconfigures_requested_streams() -> None:
    stdout = FakeStream()
    stderr = FakeStream()

    prefer_utf8_stdio(stdout, stderr)

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_prefer_utf8_stdio_ignores_streams_without_reconfigure() -> None:
    prefer_utf8_stdio(object())  # type: ignore[arg-type]
