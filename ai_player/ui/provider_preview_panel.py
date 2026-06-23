from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QGridLayout, QLabel, QStyle

PROVIDER_PREVIEW_KINDS = (
    ("asr", "_asr_preview_button", "_asr_preview_status"),
    ("translation", "_translation_preview_button", "_translation_preview_status"),
    ("tts", "_tts_preview_button", "_tts_preview_status"),
    ("speaker_gender", "_speaker_gender_preview_button", "_speaker_gender_preview_status"),
    ("ocr", "_ocr_preview_button", "_ocr_preview_status"),
    ("cleanup", "_cleanup_preview_button", "_cleanup_preview_status"),
)


def build_provider_preview_panel(owner: Any) -> None:
    preview_icon = owner.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
    buttons = {}
    statuses = {}
    for kind, button_attr, status_attr in PROVIDER_PREVIEW_KINDS:
        button = owner._make_button("provider_preview_run", preview_icon)
        button.clicked.connect(lambda _checked=False, preview_kind=kind: owner._start_provider_preview(preview_kind))
        status = owner._api_key_status_label()
        setattr(owner, button_attr, button)
        setattr(owner, status_attr, status)
        buttons[kind] = button
        statuses[kind] = status

    owner._provider_preview_buttons = buttons
    owner._provider_preview_statuses = statuses
    owner._provider_preview_status = QLabel(owner._tr("provider_preview_idle"))
    owner._provider_preview_status.setProperty("i18n_key", "provider_preview_idle")
    owner._provider_preview_status.setObjectName("apiKeyStatusLabel")
    owner._provider_preview_status.setWordWrap(True)


def add_provider_preview_row(grid: QGridLayout, owner: Any, kind: str, row: int) -> None:
    grid.addWidget(owner._provider_preview_buttons[kind], row, 0, 1, 2)
    grid.addWidget(owner._provider_preview_statuses[kind], row + 1, 0, 1, 2)
