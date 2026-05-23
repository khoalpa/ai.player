from __future__ import annotations

import json

import pytest

from ai_player.services import document_reader as docs


@pytest.mark.parametrize(("path", "expected"), [("a.pdf", True), ("a.docx", True), ("a.md", True), ("a.exe", False)])
def test_supported_document_extensions(path: str, expected: bool) -> None:
    assert docs.is_supported_document_path(path) is expected


def test_json_text_blocks_flatten_nested_values() -> None:
    blocks = docs._json_text_blocks({"title": "Demo", "items": ["one", {"two": 2}], "none": None})

    assert blocks == ["title: Demo", "items: one", "items: two: 2"]


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("One sentence.", 1),
        ("First. Second.", 1),
        ("longword " * 80, 20),
    ],
)
def test_speech_chunks_split_readable_segments(text: str, count: int) -> None:
    assert len(docs._speech_chunks(text, max_chars=40)) == count


@pytest.mark.parametrize(("seconds", "stamp"), [(0, "00:00:00,000"), (3661, "01:01:01,000")])
def test_srt_time_format(seconds: int, stamp: str) -> None:
    assert docs._srt_time(seconds) == stamp


def test_create_text_document_transcript_writes_srt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(docs, "CONFIG_DIR", tmp_path)

    transcript = docs.create_text_document_transcript("Hello. " * 30, title="Demo", seconds_per_segment=3)

    assert transcript.transcript_path.exists()
    assert transcript.segment_count >= 1
    assert "-->" in transcript.transcript_path.read_text(encoding="utf-8")


def test_read_json_file_returns_text_blocks(tmp_path) -> None:
    path = tmp_path / "demo.json"
    path.write_text(json.dumps({"a": ["b", "c"]}), encoding="utf-8")

    assert docs._read_json(path) == ["a: b", "a: c"]


def test_read_json_file_falls_back_to_text_when_invalid(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json\nsecond line", encoding="utf-8")

    assert docs._read_json(path) == ["{not-json", "second line"]
