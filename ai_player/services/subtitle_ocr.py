from __future__ import annotations

import base64
import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps

from ai_player.core.config import DEFAULT_OCR_PROVIDER, OCR_MODELS_PATH, AppConfig
from ai_player.core.value_utils import clamped_float, finite_float, nonnegative_float
from ai_player.services.ffmpeg import ffmpeg_executable

ONLINE_OCR_PROVIDERS = {"ocr_space", "azure_vision", "google_vision", "huggingface_trocr"}
OCR_SPACE_API_BASE = "https://api.ocr.space/parse/image"
GOOGLE_VISION_API_BASE = "https://vision.googleapis.com/v1/images:annotate"
HUGGINGFACE_OCR_API_BASE = "https://api-inference.huggingface.co/models"
DEFAULT_HUGGINGFACE_TROCR_MODEL = "microsoft/trocr-base-handwritten"


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
    tesseract = _tesseract_executable() if provider == "tesseract" else None
    if provider == "tesseract" and tesseract is None:
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
    if provider in {"ocrspace", "ocr_space", "ocr_space_api"}:
        return "ocr_space"
    if provider in {"azure", "azure_vision", "azure_read", "azure_ocr", "microsoft_ocr"}:
        return "azure_vision"
    if provider in {"google", "google_vision", "google_ocr", "cloud_vision"}:
        return "google_vision"
    if provider in {"hf", "huggingface", "huggingface_trocr", "trocr"}:
        return "huggingface_trocr"
    return provider


def is_online_ocr_provider(value: object) -> bool:
    return normalize_ocr_provider(str(value or "")) in ONLINE_OCR_PROVIDERS


def _ocr_frame(
    frame_path: Path,
    language: str,
    tesseract: Path | None,
    *,
    config: AppConfig | None = None,
) -> OcrFrameResult:
    frame_path = _preprocess_frame(frame_path, config=config)
    provider = normalize_ocr_provider(getattr(config, "ocr_provider", DEFAULT_OCR_PROVIDER))
    if provider in ONLINE_OCR_PROVIDERS:
        result = _ocr_frame_online(frame_path, language, provider, config=config)
        return result if _passes_confidence(result, config) else OcrFrameResult("")
    if tesseract is None:
        raise RuntimeError("Tesseract OCR executable is required for local OCR.")
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


def _ocr_frame_online(
    frame_path: Path,
    language: str,
    provider: str,
    *,
    config: AppConfig | None = None,
) -> OcrFrameResult:
    if provider == "ocr_space":
        return _ocr_frame_ocr_space(frame_path, language, config=config)
    if provider == "azure_vision":
        return _ocr_frame_azure_vision(frame_path, config=config)
    if provider == "google_vision":
        return _ocr_frame_google_vision(frame_path, language, config=config)
    if provider == "huggingface_trocr":
        return _ocr_frame_huggingface_trocr(frame_path, config=config)
    raise RuntimeError(f"Unsupported OCR provider: {provider}")


def _ocr_frame_ocr_space(frame_path: Path, language: str, *, config: AppConfig | None = None) -> OcrFrameResult:
    api_key = _ocr_api_key(config)
    url = _ocr_api_base(config) or OCR_SPACE_API_BASE
    with frame_path.open("rb") as handle:
        response = requests.post(
            url,
            headers={"apikey": api_key},
            data={
                "language": _ocr_space_language(language),
                "isOverlayRequired": "false",
                "OCREngine": "2",
            },
            files={"file": (frame_path.name, handle, _image_content_type(frame_path))},
            timeout=_ocr_timeout(config),
        )
    _raise_for_ocr_response(response, "OCR.space")
    data = _response_json(response, "OCR.space")
    if data.get("IsErroredOnProcessing"):
        errors = data.get("ErrorMessage") or data.get("ErrorDetails") or "unknown error"
        raise RuntimeError(f"OCR.space failed: {errors}")
    parsed_results = data.get("ParsedResults")
    if not isinstance(parsed_results, list) or not parsed_results:
        return OcrFrameResult("")
    text = "\n".join(str(item.get("ParsedText") or "") for item in parsed_results if isinstance(item, dict))
    return OcrFrameResult(_clean_ocr_text(text), 80.0 if text.strip() else None)


def _ocr_frame_azure_vision(frame_path: Path, *, config: AppConfig | None = None) -> OcrFrameResult:
    api_key = _ocr_api_key(config)
    url = _azure_vision_url(config)
    response = requests.post(
        url,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": _image_content_type(frame_path),
        },
        data=frame_path.read_bytes(),
        timeout=_ocr_timeout(config),
    )
    _raise_for_ocr_response(response, "Azure Vision OCR")
    data = _response_json(response, "Azure Vision OCR")
    lines: list[str] = []
    confidences: list[float] = []
    read_result = data.get("readResult") if isinstance(data, dict) else None
    blocks = read_result.get("blocks") if isinstance(read_result, dict) else []
    for block in blocks if isinstance(blocks, list) else []:
        for line in block.get("lines", []) if isinstance(block, dict) else []:
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            if text:
                lines.append(text)
            for word in line.get("words", []) if isinstance(line.get("words"), list) else []:
                if isinstance(word, dict):
                    confidence = _float_or_none(word.get("confidence"))
                    if confidence is not None:
                        confidences.append(confidence * 100 if confidence <= 1.0 else confidence)
    confidence_value = sum(confidences) / len(confidences) if confidences else (90.0 if lines else None)
    return OcrFrameResult(_clean_ocr_text(" ".join(lines)), confidence_value)


def _ocr_frame_google_vision(frame_path: Path, language: str, *, config: AppConfig | None = None) -> OcrFrameResult:
    api_key = _ocr_api_key(config)
    url = _google_vision_url(_ocr_api_base(config) or GOOGLE_VISION_API_BASE, api_key)
    payload = {
        "requests": [
            {
                "image": {"content": base64.b64encode(frame_path.read_bytes()).decode("ascii")},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {"languageHints": [_google_language_hint(language)]},
            }
        ]
    }
    response = requests.post(url, json=payload, timeout=_ocr_timeout(config))
    _raise_for_ocr_response(response, "Google Vision OCR")
    data = _response_json(response, "Google Vision OCR")
    responses = data.get("responses")
    first = responses[0] if isinstance(responses, list) and responses else {}
    if isinstance(first, dict) and first.get("error"):
        raise RuntimeError(f"Google Vision OCR failed: {first['error']}")
    text = ""
    if isinstance(first, dict):
        full_text = first.get("fullTextAnnotation")
        if isinstance(full_text, dict):
            text = str(full_text.get("text") or "")
        if not text:
            annotations = first.get("textAnnotations")
            if isinstance(annotations, list) and annotations and isinstance(annotations[0], dict):
                text = str(annotations[0].get("description") or "")
    return OcrFrameResult(_clean_ocr_text(text), 90.0 if text.strip() else None)


def _ocr_frame_huggingface_trocr(frame_path: Path, *, config: AppConfig | None = None) -> OcrFrameResult:
    api_key = _ocr_api_key(config)
    model = _huggingface_ocr_model(config)
    url = _huggingface_ocr_url(_ocr_api_base(config) or HUGGINGFACE_OCR_API_BASE, model)
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": _image_content_type(frame_path)},
        data=frame_path.read_bytes(),
        timeout=_ocr_timeout(config),
    )
    _raise_for_ocr_response(response, "Hugging Face TrOCR")
    data = response.json()
    text = _huggingface_generated_text(data)
    return OcrFrameResult(_clean_ocr_text(text), 85.0 if text.strip() else None)


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


def _ocr_api_base(config: AppConfig | None) -> str:
    return str(getattr(config, "ocr_api_base", "") or "").strip().rstrip("/")


def _ocr_api_key(config: AppConfig | None) -> str:
    api_key = str(getattr(config, "ocr_api_key", "") or "").strip()
    if not api_key:
        provider = normalize_ocr_provider(getattr(config, "ocr_provider", DEFAULT_OCR_PROVIDER))
        if provider == "ocr_space":
            return "helloworld"
        raise RuntimeError(f"OCR provider '{provider}' requires ocr_api_key.")
    return api_key


def _ocr_timeout(config: AppConfig | None) -> float:
    return max(1.0, finite_float(getattr(config, "ocr_timeout_seconds", 30.0), default=30.0))


def _azure_vision_url(config: AppConfig | None) -> str:
    api_base = _ocr_api_base(config)
    if api_base:
        if "api-version=" in api_base:
            return api_base
        return f"{api_base}/computervision/imageanalysis:analyze?api-version=2024-02-01&features=read"
    region = str(getattr(config, "ocr_api_region", "") or "eastus").strip()
    return f"https://{region}.api.cognitive.microsoft.com/computervision/imageanalysis:analyze?api-version=2024-02-01&features=read"


def _google_vision_url(api_base: str, api_key: str) -> str:
    separator = "&" if "?" in api_base else "?"
    return f"{api_base}{separator}key={api_key}"


def _huggingface_ocr_model(config: AppConfig | None) -> str:
    model = str(getattr(config, "ocr_model", "") or "").strip()
    if model and not _looks_like_local_ocr_model(model):
        return model
    return DEFAULT_HUGGINGFACE_TROCR_MODEL


def _looks_like_local_ocr_model(value: str) -> bool:
    path = Path(value)
    return path.exists() or "\\" in value or ":" in value or value.startswith((".", "/"))


def _huggingface_ocr_url(api_base: str, model: str) -> str:
    quoted_model = requests.utils.quote(model, safe="")
    if "{model}" in api_base:
        return api_base.replace("{model}", quoted_model)
    if api_base.rstrip("/").endswith(quoted_model):
        return api_base
    return f"{api_base.rstrip('/')}/{quoted_model}"


def _response_json(response: requests.Response, provider_name: str) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"{provider_name} returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{provider_name} returned an invalid JSON payload.")
    return data


def _raise_for_ocr_response(response: requests.Response, provider_name: str) -> None:
    if response.status_code < 400:
        return
    detail = ""
    try:
        detail = str(response.json())[:500]
    except Exception:
        detail = str(getattr(response, "text", "") or "")[:500]
    raise RuntimeError(f"{provider_name} request failed with HTTP {response.status_code}: {detail}")


def _image_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _ocr_space_language(language: str) -> str:
    return {
        "eng": "eng",
        "vie": "vnm",
        "jpn": "jpn",
        "chi_sim": "chs",
        "kor": "kor",
        "fra": "fre",
        "deu": "ger",
        "spa": "spa",
        "rus": "rus",
        "tha": "tha",
    }.get(language, "eng")


def _google_language_hint(language: str) -> str:
    return {
        "eng": "en",
        "vie": "vi",
        "jpn": "ja",
        "chi_sim": "zh",
        "kor": "ko",
        "fra": "fr",
        "deu": "de",
        "spa": "es",
        "rus": "ru",
        "tha": "th",
        "ind": "id",
    }.get(language, "en")


def _huggingface_generated_text(data: object) -> str:
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return str(first.get("generated_text") or first.get("text") or "")
    if isinstance(data, dict):
        return str(data.get("generated_text") or data.get("text") or "")
    return ""


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


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
