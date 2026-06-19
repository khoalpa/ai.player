from __future__ import annotations

import base64
import subprocess
from dataclasses import replace
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services import subtitle_ocr


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text="", content=b"") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.content = content

    def json(self):
        return self._payload


def test_normalize_ocr_provider_accepts_aliases() -> None:
    assert subtitle_ocr.normalize_ocr_provider("tesseract-ocr") == "tesseract"
    assert subtitle_ocr.normalize_ocr_provider("auto") == "tesseract"
    assert subtitle_ocr.normalize_ocr_provider("ocrspace") == "ocr_space"
    assert subtitle_ocr.normalize_ocr_provider("azure-read") == "azure_vision"
    assert subtitle_ocr.normalize_ocr_provider("google") == "google_vision"
    assert subtitle_ocr.normalize_ocr_provider("trocr") == "huggingface_trocr"


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


def test_ocr_video_filter_sanitizes_non_finite_config() -> None:
    config = AppConfig(
        ocr_fps=float("nan"),
        ocr_crop_top_ratio=float("inf"),
        ocr_crop_height_ratio=float("nan"),
        ocr_scale=float("inf"),
    )

    assert subtitle_ocr._ocr_video_filter(config) == "fps=0.2,crop=iw:ih*0.0500:0:ih*0.0000,scale=iw*1:ih*1,format=gray"


def test_ocr_psm_sanitizes_non_finite_config() -> None:
    assert subtitle_ocr._ocr_psm(AppConfig(ocr_psm=float("inf"))) == 6


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


def test_ocr_space_online_frame_posts_file(monkeypatch, tmp_path) -> None:
    calls = []
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(payload={"ParsedResults": [{"ParsedText": " Xin chao\n"}]})

    monkeypatch.setattr(subtitle_ocr.requests, "post", fake_post)
    monkeypatch.setattr(subtitle_ocr, "_preprocess_frame", lambda path, **_kwargs: path)

    result = subtitle_ocr._ocr_frame(
        frame,
        "vie",
        None,
        config=AppConfig(ocr_provider="ocr_space", ocr_api_key="key"),
    )

    assert result.text == "Xin chao"
    assert calls[0][0] == "https://api.ocr.space/parse/image"
    assert calls[0][1]["headers"]["apikey"] == "key"
    assert calls[0][1]["data"]["language"] == "vnm"


def test_azure_vision_online_frame_parses_read_result(monkeypatch, tmp_path) -> None:
    calls = []
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(
            payload={
                "readResult": {
                    "blocks": [
                        {"lines": [{"text": "Hello", "words": [{"confidence": 0.9}]}, {"text": "world"}]}
                    ]
                }
            }
        )

    monkeypatch.setattr(subtitle_ocr.requests, "post", fake_post)
    monkeypatch.setattr(subtitle_ocr, "_preprocess_frame", lambda path, **_kwargs: path)

    result = subtitle_ocr._ocr_frame(
        frame,
        "eng",
        None,
        config=AppConfig(ocr_provider="azure_vision", ocr_api_key="key", ocr_api_region="eastus"),
    )

    assert result.text == "Hello world"
    assert result.confidence == 90
    assert calls[0][0].startswith("https://eastus.api.cognitive.microsoft.com/")
    assert calls[0][1]["headers"]["Ocp-Apim-Subscription-Key"] == "key"


def test_google_vision_online_frame_posts_base64(monkeypatch, tmp_path) -> None:
    calls = []
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(payload={"responses": [{"fullTextAnnotation": {"text": "Google OCR"}}]})

    monkeypatch.setattr(subtitle_ocr.requests, "post", fake_post)
    monkeypatch.setattr(subtitle_ocr, "_preprocess_frame", lambda path, **_kwargs: path)

    result = subtitle_ocr._ocr_frame(
        frame,
        "eng",
        None,
        config=AppConfig(ocr_provider="google_vision", ocr_api_key="gkey"),
    )

    assert result.text == "Google OCR"
    assert "key=gkey" in calls[0][0]
    assert calls[0][1]["json"]["requests"][0]["image"]["content"] == base64.b64encode(b"png").decode("ascii")


def test_huggingface_trocr_online_frame_parses_generated_text(monkeypatch, tmp_path) -> None:
    calls = []
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(payload=[{"generated_text": "handwritten line"}])

    monkeypatch.setattr(subtitle_ocr.requests, "post", fake_post)
    monkeypatch.setattr(subtitle_ocr, "_preprocess_frame", lambda path, **_kwargs: path)

    result = subtitle_ocr._ocr_frame(
        frame,
        "eng",
        None,
        config=AppConfig(
            ocr_provider="huggingface_trocr",
            ocr_api_key="hfkey",
            ocr_model="microsoft/trocr-base-handwritten",
        ),
    )

    assert result.text == "handwritten line"
    assert calls[0][0].endswith("/microsoft%2Ftrocr-base-handwritten")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer hfkey"


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


def test_recognize_hard_subtitles_sanitizes_non_finite_timing(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_extract(_video_path, start_seconds, duration_seconds, output_pattern, *, config=None) -> None:
        captured["start"] = start_seconds
        captured["duration"] = duration_seconds
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        (output_pattern.parent / "frame-001.png").write_text("", encoding="utf-8")

    monkeypatch.setattr(subtitle_ocr, "_tesseract_executable", lambda: Path("tesseract"))
    monkeypatch.setattr(subtitle_ocr, "_extract_subtitle_frames", fake_extract)
    monkeypatch.setattr(subtitle_ocr, "_ocr_frame", lambda *_args, **_kwargs: subtitle_ocr.OcrFrameResult("Hello", 90))

    result = subtitle_ocr.recognize_hard_subtitles(
        "video.mp4",
        float("inf"),
        float("nan"),
        tmp_path,
        "en",
        AppConfig(ocr_fps=2),
    )

    assert captured == {"start": 0.0, "duration": 1.0}
    assert result == [subtitle_ocr.OcrSubtitleSegment(start=0.0, end=1.0, text="Hello")]
