from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QTextEdit, QVBoxLayout

from ai_player.ui.player_window_utils import UI_TEXT


class CacheProgressDialog(QDialog):
    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self._language = language
        self._started_at = time.monotonic()
        self._last_status = ""
        self.setWindowTitle(self._tr("cache_dialog_title"))
        self.setModal(False)
        self.resize(620, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._summary = QLabel(self)
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        layout.addWidget(self._progress)

        self._detail = QLabel(self)
        self._detail.setWordWrap(True)
        layout.addWidget(self._detail)

        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        layout.addWidget(self._log, 1)

    def update_cache(self, data: dict) -> None:
        status = str(data.get("status") or "")
        provider = str(data.get("provider") or "")
        quality = str(data.get("quality") or "")
        cache_dir = str(data.get("cache_dir") or "")
        filename = str(data.get("filename") or "")
        downloaded = _int_value(data.get("downloaded_bytes"))
        total = _int_value(data.get("total_bytes"))
        speed = _float_value(data.get("speed"))
        eta = _int_value(data.get("eta"))

        self._summary.setText(
            "\n".join(
                item
                for item in (
                    f"{self._tr('cache_provider')}: {provider or '-'}",
                    f"{self._tr('cache_quality')}: {quality or '-'}",
                    f"{self._tr('cache_folder')}: {cache_dir or '-'}",
                    f"{self._tr('cache_file')}: {Path(filename).name if filename else '-'}",
                )
                if item
            )
        )

        if total and downloaded is not None:
            percent = max(0, min(100, int(downloaded * 100 / max(1, total))))
            self._progress.setRange(0, 100)
            self._progress.setValue(percent)
        elif status in {"finished", "cached"}:
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
        else:
            self._progress.setRange(0, 0)

        detail_parts = [self._status_text(status)]
        if downloaded is not None:
            size_text = _format_bytes(downloaded)
            if total:
                size_text += f" / {_format_bytes(total)}"
            detail_parts.append(size_text)
        if speed:
            detail_parts.append(f"{self._tr('cache_speed')}: {_format_bytes(speed)}/s")
        if eta is not None:
            detail_parts.append(f"{self._tr('cache_eta')}: {_format_seconds(eta)}")
        detail_parts.append(f"{self._tr('cache_elapsed')}: {_format_seconds(time.monotonic() - self._started_at)}")
        self._detail.setText(" | ".join(detail_parts))

        if status and status != self._last_status:
            self._last_status = status
            self._log.append(self._status_text(status))

    def mark_failed(self, message: str) -> None:
        self._progress.setRange(0, 100)
        self._detail.setText(f"{self._tr('cache_failed')}: {message}")
        self._log.append(f"{self._tr('cache_failed')}: {message}")

    def _status_text(self, status: str) -> str:
        return self._tr(f"cache_status_{status}") if status else self._tr("cache_status_starting")

    def _tr(self, key: str) -> str:
        fallback = UI_TEXT.get("vi", {})
        return UI_TEXT.get(self._language, fallback).get(key, fallback.get(key, key))


def _int_value(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _float_value(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(max(0.0, value))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _format_seconds(value: float) -> str:
    seconds = max(0, int(value))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
