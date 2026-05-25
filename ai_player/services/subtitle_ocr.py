from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageOps

from ai_player.core.config import DEFAULT_OCR_PROVIDER, OCR_MODELS_PATH, AppConfig
from ai_player.core.value_utils import clamped_float, nonnegative_float
from ai_player.services.ffmpeg import ffmpeg_executable


@dataclass(frozen=True)
class OcrSubtitleSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class OcrFrameResult:
    text: str
    confidence: float | None = None


def recognize_hard_subtitles(
    video_path: str,
    start_seconds: float,
    duration_seconds: int,
    work_dir: Path,
    source_language: str = "auto",
    config: AppConfig | None = None,
) -> list[OcrSubtitleSegment]:
    provider = normalize_ocr_provider(config.ocr_provider if config is not None else DEFAULT_OCR_PROVIDER)
    if provider != "tesseract":
        raise RuntimeError(f"OCR provider '{provider}' is not supported yet. Select Tesseract OCR.")

    tesseract = _tesseract_executable()
    if tesseract is None:
        raise RuntimeError(
            "Chưa tìm thấy Tesseract OCR trong PATH. Cài Tesseract OCR và gói ngôn ngữ cần dùng, "
            "hoặc chuyển Nguồn sang Âm gốc/Transcript."
        )

    safe_start = _seconds_value(start_seconds, default=0.0)
    safe_duration = _duration_value(duration_seconds, default=1.0)
    frame_dir = work_dir / f"subtitle-{int(safe_start * 1000)}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    pattern = frame_dir / "frame-%03d.png"
    _extract_subtitle_frames(video_path, safe_start, safe_duration, pattern, config=config)

    lang = _tesseract_language(source_language)
    entries: list[tuple[OcrSubtitleSegment, float | None]] = []
    frame_step = 1.0 / _ocr_fps(config)
    for index, frame_path in enumerate(sorted(frame_dir.glob("frame-*.png"))):
        result = _ocr_frame(frame_path, lang, tesseract, config=config)
        text = result.text
        key = _text_key(text)
        if not key:
            continue
        frame_start = safe_start + index * frame_step
        frame_end = min(safe_start + safe_duration, frame_start + 2.0)
        if entries and _same_subtitle(entries[-1][0].text, text, _ocr_merge_similarity(config)):
            previous, previous_confidence = entries[-1]
            best_text = _best_text(previous.text, previous_confidence, text, result.confidence)
            best_confidence = _best_confidence(previous_confidence, result.confidence)
            entries[-1] = (
                OcrSubtitleSegment(previous.start, max(previous.end, frame_end), best_text),
                best_confidence,
            )
            continue
        entries.append((OcrSubtitleSegment(start=frame_start, end=frame_end, text=text), result.confidence))
    return [segment for segment, _confidence in entries]


def _extract_subtitle_frames(
    video_path: str,
    start_seconds: float,
    duration_seconds: int,
    output_pattern: Path,
    *,
    config: AppConfig | None = None,
) -> None:
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{_seconds_value(start_seconds, default=0.0):.3f}",
        "-t",
        str(int(_duration_value(duration_seconds, default=1.0))),
        "-i",
        video_path,
        "-vf",
        _ocr_video_filter(config),
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
        raise RuntimeError(f"Không tách được khung hình để OCR phụ đề. {detail}") from exc


def normalize_ocr_provider(value: str | None) -> str:
    provider = str(value or DEFAULT_OCR_PROVIDER).strip().lower().replace("-", "_")
    if provider in {"", "auto"}:
        return DEFAULT_OCR_PROVIDER
    if provider in {"tesseract", "tesseract_ocr"}:
        return "tesseract"
    return provider


def _ocr_frame(frame_path: Path, language: str, tesseract: Path, *, config: AppConfig | None = None) -> OcrFrameResult:
    frame_path = _preprocess_frame(frame_path, config=config)
    tessdata_dir = _tessdata_dir(config)
    process = _run_tesseract_tsv(frame_path, language, tesseract, tessdata_dir, _ocr_psm(config))
    if process.returncode != 0 and language != "eng":
        process = _run_tesseract_tsv(frame_path, "eng", tesseract, tessdata_dir, _ocr_psm(config))
    if process.returncode == 0:
        result = _parse_tesseract_tsv(process.stdout)
        if result.text:
            return result if _passes_confidence(result, config) else OcrFrameResult("")

    process = _run_tesseract_stdout(frame_path, language, tesseract, tessdata_dir, _ocr_psm(config))
    if process.returncode != 0 and language != "eng":
        process = _run_tesseract_stdout(frame_path, "eng", tesseract, tessdata_dir, _ocr_psm(config))
    text = _clean_ocr_text(process.stdout if process.returncode == 0 else "")
    return OcrFrameResult(text=text, confidence=None)


def _run_tesseract_tsv(
    frame_path: Path,
    language: str,
    tesseract: Path,
    tessdata_dir: Path | None,
    psm: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(tesseract),
        str(frame_path),
        "stdout",
        "-l",
        language,
        "--psm",
        str(psm),
        "tsv",
    ]
    if tessdata_dir is not None:
        command.extend(["--tessdata-dir", str(tessdata_dir)])
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _run_tesseract_stdout(
    frame_path: Path,
    language: str,
    tesseract: Path,
    tessdata_dir: Path | None,
    psm: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(tesseract),
        str(frame_path),
        "stdout",
        "-l",
        language,
        "--psm",
        str(psm),
    ]
    if tessdata_dir is not None:
        command.extend(["--tessdata-dir", str(tessdata_dir)])
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


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


def _tessdata_dir(config: AppConfig | None = None) -> Path | None:
    configured = Path(config.ocr_model) if config is not None and config.ocr_model else None
    candidates = [
        configured,
        OCR_MODELS_PATH / "tessdata",
        OCR_MODELS_PATH / "tessdata_best",
        Path("C:/Program Files/Tesseract-OCR/tessdata"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tessdata"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return None


def _preprocess_frame(frame_path: Path, *, config: AppConfig | None = None) -> Path:
    processed = frame_path.with_name(f"{frame_path.stem}-ocr{frame_path.suffix}")
    try:
        with Image.open(frame_path) as image:
            gray = ImageOps.grayscale(image)
            enhanced = ImageOps.autocontrast(gray)
            if _ocr_threshold(config):
                enhanced = enhanced.point(lambda pixel: 255 if pixel >= 145 else 0)
            enhanced.save(processed)
    except OSError:
        return frame_path
    return processed


def _parse_tesseract_tsv(value: str) -> OcrFrameResult:
    lines = [line for line in (value or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return OcrFrameResult("")
    header = lines[0].split("\t")
    try:
        confidence_index = header.index("conf")
        text_index = header.index("text")
    except ValueError:
        return OcrFrameResult("")

    words: list[str] = []
    confidence_sum = 0.0
    confidence_weight = 0
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) <= max(confidence_index, text_index):
            continue
        text = columns[text_index].strip()
        if not text:
            continue
        try:
            confidence = float(columns[confidence_index])
        except ValueError:
            confidence = -1.0
        if confidence < 0:
            continue
        words.append(text)
        weight = max(1, len(text))
        confidence_sum += confidence * weight
        confidence_weight += weight

    cleaned = _clean_ocr_text(" ".join(words))
    confidence_value = confidence_sum / confidence_weight if confidence_weight else None
    return OcrFrameResult(cleaned, confidence_value)


def _passes_confidence(result: OcrFrameResult, config: AppConfig | None) -> bool:
    if result.confidence is None:
        return True
    return result.confidence >= _ocr_min_confidence(config)


def _clean_ocr_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"^[^\w\u0080-\uffff]+|[^\w\u0080-\uffff.!?。？！]+$", "", text)
    return text


def _text_key(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold(), flags=re.UNICODE)


def _same_subtitle(left: str, right: str, threshold: float) -> bool:
    left_key = _text_key(left)
    right_key = _text_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= threshold


def _best_text(left: str, left_confidence: float | None, right: str, right_confidence: float | None) -> str:
    if right_confidence is not None and left_confidence is not None and right_confidence > left_confidence:
        return right
    if left_confidence is None and right_confidence is not None:
        return right
    if right_confidence == left_confidence and len(right) > len(left):
        return right
    return left


def _best_confidence(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


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


def _ocr_video_filter(config: AppConfig | None) -> str:
    fps = _ocr_fps(config)
    crop_top = _clamp_float(getattr(config, "ocr_crop_top_ratio", 0.58), 0.0, 0.95)
    crop_height = _clamp_float(getattr(config, "ocr_crop_height_ratio", 0.38), 0.05, 1.0 - crop_top)
    scale = _clamp_float(getattr(config, "ocr_scale", 2.0), 1.0, 4.0)
    return f"fps={fps:g},crop=iw:ih*{crop_height:.4f}:0:ih*{crop_top:.4f},scale=iw*{scale:g}:ih*{scale:g},format=gray"


def _ocr_fps(config: AppConfig | None) -> float:
    return _clamp_float(getattr(config, "ocr_fps", 2.0), 0.2, 10.0)


def _ocr_psm(config: AppConfig | None) -> int:
    try:
        psm = int(getattr(config, "ocr_psm", 6))
    except (OverflowError, TypeError, ValueError):
        psm = 6
    return max(3, min(13, psm))


def _ocr_threshold(config: AppConfig | None) -> bool:
    return bool(getattr(config, "ocr_threshold", True))


def _ocr_min_confidence(config: AppConfig | None) -> float:
    return _clamp_float(getattr(config, "ocr_min_confidence", 35.0), 0.0, 100.0)


def _ocr_merge_similarity(config: AppConfig | None) -> float:
    return _clamp_float(getattr(config, "ocr_merge_similarity", 0.86), 0.0, 1.0)


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    return clamped_float(value, minimum=minimum, maximum=maximum)


def _seconds_value(value: object, *, default: float) -> float:
    return nonnegative_float(value, default=default)


def _duration_value(value: object, *, default: float) -> float:
    return max(1.0, _seconds_value(value, default=default))
