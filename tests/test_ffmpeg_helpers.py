from pathlib import Path

from ai_player.services.ffmpeg import concat_escape, concat_file_line, safe_float


def test_concat_escape_uses_forward_slashes_and_quotes() -> None:
    escaped = concat_escape(Path("C:/Video/Test O'Clock/demo.wav"))

    assert "/" in escaped
    assert "\\Users\\" not in escaped
    assert "O'\\''Clock" in escaped


def test_concat_file_line_format() -> None:
    line = concat_file_line(Path("demo.wav"))

    assert line.startswith("file '")
    assert line.endswith("'\n")


def test_safe_float() -> None:
    assert safe_float("1.25") == 1.25
    assert safe_float("N/A") is None
    assert safe_float("-1") is None
