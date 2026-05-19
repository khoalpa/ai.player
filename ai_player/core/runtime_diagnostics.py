from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import MODEL_ROOT, OCR_MODELS_PATH, PROJECT_ROOT


@dataclass(frozen=True)
class DiagnosticItem:
    name: str
    status: str
    detail: str
    required: bool = False


@dataclass(frozen=True)
class DiagnosticSection:
    title: str
    items: tuple[DiagnosticItem, ...]


@dataclass(frozen=True)
class RuntimeDiagnostics:
    python: str
    project_root: Path
    sections: tuple[DiagnosticSection, ...]

    @property
    def failure_count(self) -> int:
        return sum(1 for section in self.sections for item in section.items if item.required and item.status == "MISS")


PYTHON_PACKAGES = (
    "PySide6",
    "fitz",
    "PIL",
    "soundcard",
    "faster_whisper",
    "ctranslate2",
    "transformers",
    "edge_tts",
)

TOOLS = {
    "ffmpeg": ("ffmpeg",),
    "ffplay": ("ffplay",),
    "tesseract": (
        "tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ),
    "soffice": (
        "soffice",
        "libreoffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ),
}

REQUIRED_TOOLS = {"ffmpeg", "ffplay"}

MODEL_PATHS = {
    "Whisper": MODEL_ROOT / "asr" / "faster-whisper-base",
    "NLLB": MODEL_ROOT / "translation" / "nllb-200-distilled-600M",
    "VieNeu standard": MODEL_ROOT / "tts" / "vieneu" / "standard",
    "VieNeu turbo": MODEL_ROOT / "tts" / "vieneu" / "turbo",
}

TESSDATA = OCR_MODELS_PATH / "tessdata"


def collect_runtime_diagnostics(*, include_audio_devices: bool = True) -> RuntimeDiagnostics:
    sections = [
        _package_section(),
        _tool_section(),
        _model_section(),
        _tessdata_section(),
    ]
    if include_audio_devices:
        sections.append(_audio_capture_section())
    return RuntimeDiagnostics(
        python=sys.executable,
        project_root=PROJECT_ROOT,
        sections=tuple(sections),
    )


def format_runtime_diagnostics(report: RuntimeDiagnostics) -> str:
    lines = [
        "AI Player runtime doctor",
        f"Python: {report.python}",
        f"Project: {report.project_root}",
        "",
    ]
    for section in report.sections:
        lines.append(section.title)
        for item in section.items:
            label = _display_status(item)
            detail = f": {item.detail}" if item.detail else ""
            lines.append(f"  {label} {item.name}{detail}")
        lines.append("")
    if report.failure_count:
        lines.append(f"FAILED: {report.failure_count} required runtime item(s) are missing.")
    else:
        lines.append("OK: required runtime items are available.")
    return "\n".join(lines)


def format_runtime_diagnostics_summary(report: RuntimeDiagnostics) -> str:
    lines = []
    for section in report.sections:
        missing = sum(1 for item in section.items if item.status == "MISS")
        warnings = sum(1 for item in section.items if item.status == "WARN")
        if missing:
            lines.append(f"{section.title}: thiếu {missing}")
        elif warnings:
            lines.append(f"{section.title}: cảnh báo {warnings}")
        else:
            lines.append(f"{section.title}: OK")
    if report.failure_count:
        lines.append(f"Kết luận: thiếu {report.failure_count} mục bắt buộc")
    else:
        lines.append("Kết luận: runtime bắt buộc đã sẵn sàng")
    return "\n".join(lines)


def _package_section() -> DiagnosticSection:
    items = []
    for package in PYTHON_PACKAGES:
        ok = importlib.util.find_spec(package) is not None
        items.append(DiagnosticItem(package, "OK" if ok else "MISS", "", required=True))
    return DiagnosticSection("Python packages", tuple(items))


def _tool_section() -> DiagnosticSection:
    items = []
    for name, candidates in TOOLS.items():
        found = _first_tool(candidates)
        required = name in REQUIRED_TOOLS
        if found:
            status = "OK"
            detail = found
        else:
            status = "MISS" if required else "WARN"
            detail = "not found"
        items.append(DiagnosticItem(name, status, detail, required=required))
    return DiagnosticSection("External tools", tuple(items))


def _model_section() -> DiagnosticSection:
    items = []
    for name, path in MODEL_PATHS.items():
        ok = path.exists() and any(path.iterdir())
        items.append(DiagnosticItem(name, "OK" if ok else "WARN", str(path)))
    return DiagnosticSection("Local model/cache folders", tuple(items))


def _tessdata_section() -> DiagnosticSection:
    langs = sorted(path.stem for path in TESSDATA.glob("*.traineddata")) if TESSDATA.exists() else []
    if langs:
        item = DiagnosticItem(str(TESSDATA), "OK", ", ".join(langs))
    else:
        item = DiagnosticItem(str(TESSDATA), "WARN", "no local *.traineddata files")
    return DiagnosticSection("Tesseract language packs", (item,))


def _audio_capture_section() -> DiagnosticSection:
    try:
        import soundcard as sc

        speakers = sc.all_speakers()
        microphones = sc.all_microphones(include_loopback=True)
    except Exception as exc:
        return DiagnosticSection(
            "Audio capture",
            (DiagnosticItem("soundcard device scan", "WARN", str(exc)),),
        )
    return DiagnosticSection(
        "Audio capture",
        (
            DiagnosticItem("speakers", "OK", str(len(speakers))),
            DiagnosticItem("microphones/loopbacks", "OK", str(len(microphones))),
        ),
    )


def _first_tool(candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        path = Path(candidate)
        if path.exists():
            return str(path)
    return ""


def _display_status(item: DiagnosticItem) -> str:
    if item.status == "OK":
        return "OK  "
    return item.status
