from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext


from PySide6.QtWidgets import QGridLayout, QLabel, QStyle

PROVIDER_PREVIEW_KINDS = (
    ("asr", "_asr_preview_button", "_asr_preview_status"),
    ("translation", "_translation_preview_button", "_translation_preview_status"),
    ("tts", "_tts_preview_button", "_tts_preview_status"),
    ("speaker_gender", "_speaker_gender_preview_button", "_speaker_gender_preview_status"),
    ("ocr", "_ocr_preview_button", "_ocr_preview_status"),
    ("cleanup", "_cleanup_preview_button", "_cleanup_preview_status"),
)


def build_provider_preview_panel(owner: WindowContext) -> None:
    preview_icon = owner.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
    buttons = {}
    statuses = {}
    for kind, button_attr, status_attr in PROVIDER_PREVIEW_KINDS:
        button = owner.ui._make_button("provider_preview_run", preview_icon)
        button.clicked.connect(
            lambda _checked=False, preview_kind=kind: owner.provider_preview._start_provider_preview(preview_kind)
        )
        status = owner.ui._api_key_status_label()
        owner.set(button_attr, button)
        owner.set(status_attr, status)
        buttons[kind] = button
        statuses[kind] = status

    owner.window._provider_preview_buttons = buttons
    owner.window._provider_preview_statuses = statuses
    owner.window._provider_preview_status = QLabel(owner.settings._tr("provider_preview_idle"))
    owner.window._provider_preview_status.setProperty("i18n_key", "provider_preview_idle")
    owner.window._provider_preview_status.setObjectName("apiKeyStatusLabel")
    owner.window._provider_preview_status.setWordWrap(True)


def add_provider_preview_row(grid: QGridLayout, owner: WindowContext, kind: str, row: int) -> None:
    grid.addWidget(owner.window._provider_preview_buttons[kind], row, 0, 1, 2)
    grid.addWidget(owner.window._provider_preview_statuses[kind], row + 1, 0, 1, 2)
