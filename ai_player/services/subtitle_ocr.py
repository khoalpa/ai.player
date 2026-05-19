from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import PROJECT_ROOT
from ai_player.services.ffmpeg import ffmpeg_executable


@dataclass(frozen=True)
class OcrSubtitleSegment:
    start: float
    end: float
    text: str


def recognize_hard_subtitles(
    video_path: str,
    start_seconds: float,
    duration_seconds: int,
    work_dir: Path,
    source_language: str = "auto",
) -> list[OcrSubtitleSegment]:
    tesseract = _tesseract_executable()
    if tesseract is None:
        raise RuntimeError(
            "Chưa tìm thấy Tesseract OCR trong PATH. Cài Tesseract OCR và gói ngôn ngữ cần dùng, "
            "hoặc chuyển Nguồn sang Âm gốc/Transcript."
        )

    frame_dir = work_dir / f"subtitle-{int(start_seconds * 1000)}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    pattern = frame_dir / "frame-%03d.png"
    _extract_subtitle_frames(video_path, start_seconds, duration_seconds, pattern)

    lang = _tesseract_language(source_language)
    entries: list[OcrSubtitleSegment] = []
    last_key = ""
    for index, frame_path in enumerate(sorted(frame_dir.glob("frame-*.png"))):
        text = _ocr_frame(frame_path, lang, tesseract)
        key = _text_key(text)
        if not key or key == last_key:
            continue
        frame_start = start_seconds + index * 0.5
        entries.append(
            OcrSubtitleSegment(
                start=frame_start,
                end=min(start_seconds + duration_seconds, frame_start + 2.0),
                text=text,
            )
        )
        last_key = key
    return entries


def _extract_subtitle_frames(
    video_path: str,
    start_seconds: float,
    duration_seconds: int,
    output_pattern: Path,
) -> None:
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        str(max(1, int(duration_seconds))),
        "-i",
        video_path,
        "-vf",
        "fps=2,crop=iw:ih*0.38:0:ih*0.58,scale=iw*2:ih*2,format=gray",
        "-y",
        str(output_pattern),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        suffix = Path(video_path).suffix.lower()
        if suffix in {".ppt", ".pptx", ".doc", ".docx", ".pdf", ".txt", ".md", ".rtf", ".csv", ".json"}:
            raise RuntimeError(
                "Tệp đang mở là tài liệu, không phải video. Hãy mở bằng nút 'Mở tài liệu' "
                "hoặc để app tự chuyển Nguồn sang Transcript."
            ) from exc
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Không tách được khung hình đẻ OCR phụ đề. {detail}") from exc


def _ocr_frame(frame_path: Path, language: str, tesseract: Path) -> str:
    tessdata_dir = _tessdata_dir()
    command = [
        str(tesseract),
        str(frame_path),
        "stdout",
        "-l",
        language,
        "--psm",
        "6",
    ]
    if tessdata_dir is not None:
        command.extend(["--tessdata-dir", str(tessdata_dir)])
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode != 0 and language != "eng":
        fallback = [
            str(tesseract),
            str(frame_path),
            "stdout",
            "-l",
            "eng",
            "--psm",
            "6",
        ]
        if tessdata_dir is not None:
            fallback.extend(["--tessdata-dir", str(tessdata_dir)])
        process = subprocess.run(
            fallback,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    return _clean_ocr_text(process.stdout if process.returncode == 0 else "")


def _tesseract_executable() -> Path | None:
    found = shutil.which("tesseract")
    if found:
        return Path(found)
    for candidate in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if candidate.exists():
            return candidate
    return None


def _tessdata_dir() -> Path | None:
    candidates = [
        PROJECT_ROOT / "models" / "ocr" / "tessdata",
        Path("C:/Program Files/Tesseract-OCR/tessdata"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tessdata"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _clean_ocr_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"^[^\w\u0080-\uffff]+|[^\w\u0080-\uffff.!?。？！]+$", "", text)
    return text


def _text_key(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold(), flags=re.UNICODE)


def _tesseract_language(source_language: str) -> str:
    language = str(source_language or "auto").strip().lower().split("-")[0]
    return {
        "auto": "eng",
        "en": "eng",
        "ja": "jpn",
        "zh": "chi_sim",
        "ko": "kor",
        "fr": "fra",
        "de": "deu",
        "es": "spa",
        "ru": "rus",
        "th": "tha",
        "id": "ind",
        "vi": "vie",
    }.get(language, "eng")
