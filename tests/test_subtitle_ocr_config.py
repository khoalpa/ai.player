from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services import subtitle_ocr


def test_normalize_ocr_provider_accepts_aliases() -> None:
    assert subtitle_ocr.normalize_ocr_provider("tesseract-ocr") == "tesseract"
    assert subtitle_ocr.normalize_ocr_provider("auto") == "tesseract"


def test_tessdata_dir_prefers_configured_model(tmp_path) -> None:
    configured = tmp_path / "custom-tessdata"
    configured.mkdir()
    config = replace(AppConfig(), ocr_model=str(configured))

    assert subtitle_ocr._tessdata_dir(config) == configured


def test_tesseract_language_maps_vietnamese() -> None:
    assert subtitle_ocr._tesseract_language("vi-VN") == "vie"


def test_ocr_video_filter_uses_configurable_sampling_window() -> None:
    config = AppConfig(ocr_fps=3, ocr_crop_top_ratio=0.5, ocr_crop_height_ratio=0.25, ocr_scale=1.5)

    assert (
        subtitle_ocr._ocr_video_filter(config) == "fps=3,crop=iw:ih*0.2500:0:ih*0.5000,scale=iw*1.5:ih*1.5,format=gray"
    )


def test_parse_tesseract_tsv_keeps_text_and_confidence() -> None:
    result = subtitle_ocr._parse_tesseract_tsv("level\tconf\ttext\n5\t91.5\tHELLO\n5\t82.0\tWORLD\n5\t-1\t\n")

    assert result.text == "HELLO WORLD"
    assert result.confidence is not None
    assert round(result.confidence, 1) == 86.8


def test_ocr_frame_drops_low_confidence_text(monkeypatch, tmp_path) -> None:
    frame = tmp_path / "frame.png"
    frame.write_text("not an image", encoding="utf-8")
    tsv = "level\tconf\ttext\n5\t10\tNOISE\n"
    config = AppConfig(ocr_min_confidence=50)

    monkeypatch.setattr(subtitle_ocr, "_tessdata_dir", lambda _config: None)
    monkeypatch.setattr(
        subtitle_ocr,
        "_run_tesseract_tsv",
        lambda *_args: subprocess.CompletedProcess(args=[], returncode=0, stdout=tsv),
    )
    monkeypatch.setattr(
        subtitle_ocr,
        "_run_tesseract_stdout",
        lambda *_args: subprocess.CompletedProcess(args=[], returncode=0, stdout="NOISE"),
    )

    result = subtitle_ocr._ocr_frame(frame, "eng", Path("tesseract"), config=config)

    assert result.text == ""


def test_recognize_hard_subtitles_merges_similar_frames(monkeypatch, tmp_path) -> None:
    recognized = iter(
        [
            subtitle_ocr.OcrFrameResult("Xin chao Viet Nam", 70),
            subtitle_ocr.OcrFrameResult("Xin chao Viet Nam.", 80),
            subtitle_ocr.OcrFrameResult("Xin chao Viet Nam", 75),
        ]
    )

    def fake_extract(_video_path, _start_seconds, _duration_seconds, output_pattern, *, config=None) -> None:
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(1, 4):
            (output_pattern.parent / f"frame-{index:03d}.png").write_text("", encoding="utf-8")

    monkeypatch.setattr(subtitle_ocr, "_tesseract_executable", lambda: Path("tesseract"))
    monkeypatch.setattr(subtitle_ocr, "_extract_subtitle_frames", fake_extract)
    monkeypatch.setattr(subtitle_ocr, "_ocr_frame", lambda *_args, **_kwargs: next(recognized))

    result = subtitle_ocr.recognize_hard_subtitles(
        "video.mp4",
        0,
        3,
        tmp_path,
        "vi",
        AppConfig(ocr_fps=2, ocr_merge_similarity=0.85),
    )

    assert result == [subtitle_ocr.OcrSubtitleSegment(start=0.0, end=3, text="Xin chao Viet Nam.")]
