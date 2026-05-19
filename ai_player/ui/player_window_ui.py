from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QWidget,
)

from ai_player.ui.player_window_utils import UI_TEXT, UI_TEXT_ALIASES
from ai_player.ui.player_window_utils import ui_label as _ui_label


class PlayerUiMixin:
    def _i18n_text(self, key_or_text: str) -> str:
        language = self._config.gui_language
        if hasattr(self, "_ui_language_combo"):
            language = self._ui_language()
        fallback = UI_TEXT.get("vi", {})
        strings = UI_TEXT.get(language, fallback)
        return strings.get(key_or_text, fallback.get(key_or_text, _ui_label(key_or_text)))

    def _make_button(self, text: str, icon: QIcon) -> QPushButton:
        label = self._i18n_text(text)
        button = QPushButton(icon, label)
        key = text if text in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(text) or UI_TEXT_ALIASES.get(label)
        if key:
            button.setProperty("i18n_key", key)
        button.setMinimumHeight(36)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @staticmethod
    def _compact_combo(combo: QComboBox) -> None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _option_combo(self, options: list[tuple[str, str]], current: str) -> QComboBox:
        combo = QComboBox()
        self._compact_combo(combo)
        for label, value in options:
            combo.addItem(_ui_label(label), value)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    def _device_combo(self, devices: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        self._compact_combo(combo)
        combo.setEditable(True)
        combo.addItem("Auto", "")
        for device in devices:
            if device:
                combo.addItem(device, device)
        if current:
            index = combo.findData(current)
            if index < 0:
                combo.addItem(current, current)
                index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
        else:
            combo.setCurrentIndex(0)
        return combo

    def _audio_source_panel(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        layout.addWidget(self._field_label("source"), 0, 0)
        layout.addWidget(self._audio_source_combo, 0, 1)
        layout.addWidget(self._field_label("transcript"), 1, 0)
        layout.addWidget(self._transcript_path_row(), 1, 1)
        self._sync_audio_source_controls()
        return panel

    def _transcript_path_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._transcript_path_edit, 1)
        layout.addWidget(self._transcript_file_button)
        return row

    def _labeled_slider(
        self,
        *,
        minimum: int,
        maximum: int,
        step: int,
        value: int,
        formatter,
    ) -> tuple[QSlider, QLabel]:
        slider = self._value_slider(minimum=minimum, maximum=maximum, step=step, value=value)
        label = self._value_label(formatter(value))
        slider.valueChanged.connect(lambda new_value: label.setText(formatter(new_value)))
        return slider, label

    @staticmethod
    def _value_slider(*, minimum: int, maximum: int, step: int, value: int) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setSingleStep(step)
        slider.setPageStep(step)
        slider.setTickInterval(step)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setValue(value)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return slider

    @staticmethod
    def _value_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("valueLabel")
        label.setMinimumWidth(54)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return label

    @staticmethod
    def _slider_row(slider: QSlider, value_label: QLabel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        return row

    def _icon_button(self, icon: QStyle.StandardPixmap, tooltip: str) -> QPushButton:
        button = QPushButton(self.style().standardIcon(icon), "")
        button.setToolTip(self._i18n_text(tooltip))
        key = tooltip if tooltip in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(tooltip)
        if key:
            button.setProperty("i18n_tooltip_key", key)
        button.setFixedSize(38, 36)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _field_label(self, text: str) -> QLabel:
        label_text = self._i18n_text(text)
        label = QLabel(label_text)
        key = text if text in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(text) or UI_TEXT_ALIASES.get(label_text)
        if key:
            label.setProperty("i18n_key", key)
        label.setObjectName("fieldLabel")
        return label

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(self._i18n_text(text))
        if text in UI_TEXT.get("vi", {}):
            label.setProperty("i18n_key", text)
        label.setObjectName("sectionTitle")
        label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        return label

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#root {
                background: #f3f3f3;
                color: #1f1f1f;
                font-family: "Segoe UI Variable", "Segoe UI", "Arial";
                font-size: 10pt;
            }
            QFrame#sourceBar, QFrame#sidePanel, QFrame#videoPanel {
                background: #ffffff;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
            }
            QFrame#mediaFrame {
                background: #ffffff;
                border-radius: 4px;
            }
            QFrame#videoPlaceholder {
                background: #ffffff;
                border-radius: 4px;
            }
            QLabel#subtitleOverlay {
                background: transparent;
                color: #ffffff;
                border: 0;
                outline: 0;
                padding: 0;
                margin: 0;
                font-size: 24px;
                font-weight: 800;
            }
            QFrame#sourceBar {
                background: #fbfbfb;
            }
            QScrollArea#sideScroll {
                background: transparent;
                border: 0;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 4px 2px 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: #c9c9c9;
                border-radius: 5px;
                min-height: 32px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QLabel#appTitle {
                color: #1f1f1f;
                font-size: 18pt;
                font-weight: 700;
            }
            QLabel#sourceLabel {
                color: #5f5f5f;
                padding-left: 8px;
            }
            QLabel#sectionTitle {
                color: #1f1f1f;
            }
            QLabel#fieldLabel {
                color: #616161;
                font-size: 9pt;
            }
            QLabel#valueLabel {
                color: #323130;
                font-size: 9pt;
            }
            QVideoWidget#videoSurface {
                background: #ffffff;
                border-radius: 4px;
            }
            QFrame#controls {
                background: #fafafa;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
            }
            QTextEdit#transcript {
                background: #ffffff;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 10px;
                selection-background-color: #0067c0;
            }
            QTextEdit#documentView {
                background: #ffffff;
                color: #1f1f1f;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 28px;
                font-size: 16pt;
                line-height: 1.45;
                selection-background-color: #0067c0;
            }
            QTabWidget#settingsTabs::pane {
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #f5f5f5;
                color: #616161;
                border: 1px solid #e5e5e5;
                border-bottom: 0;
                padding: 8px 14px;
                margin-right: 4px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                min-width: 78px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0067c0;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #ffffff;
                color: #0067c0;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d1d1d1;
                border-radius: 6px;
                padding: 8px 12px;
                color: #1f1f1f;
            }
            QPushButton:hover {
                background: #f5f5f5;
                border-color: #c7c7c7;
            }
            QPushButton:pressed, QPushButton:checked {
                background: #e8f3ff;
                border-color: #0067c0;
                color: #004578;
            }
            QPushButton#primaryButton {
                background: #0067c0;
                border-color: #0067c0;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: #005a9e;
                border-color: #005a9e;
            }
            QPushButton#dubButton:checked {
                background: #e6f4ea;
                border-color: #107c10;
                color: #0b5a0b;
                font-weight: 600;
            }
            QComboBox, QLineEdit {
                background: #ffffff;
                border: 1px solid #d1d1d1;
                border-radius: 6px;
                padding: 7px 10px;
                min-height: 26px;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #a6a6a6;
            }
            QComboBox:focus, QLineEdit:focus {
                border-color: #0067c0;
            }
            QComboBox:disabled, QLineEdit:disabled {
                color: #8a8a8a;
                background: #f5f5f5;
            }
            QCheckBox {
                color: #323130;
                spacing: 8px;
                padding: 5px 0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:checked {
                background: #0067c0;
                border: 1px solid #0067c0;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                background: #ffffff;
                border: 1px solid #8a8a8a;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked:hover {
                border-color: #0067c0;
            }
            QSlider::groove:horizontal {
                height: 7px;
                background: #e5e5e5;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
                background: #0067c0;
            }
            QSlider::handle:horizontal:hover {
                background: #005a9e;
            }
            QLabel#timeLabel {
                color: #323130;
                font-weight: 600;
            }
            QStatusBar {
                background: #f3f3f3;
                color: #616161;
                border-top: 1px solid #e5e5e5;
            }
            """
        )

    def _set_dubbing_ready(self, ready: bool, message: str = "") -> None:
        self._dubbing_ready = ready
        if hasattr(self, "_play_button"):
            self._play_button.setEnabled(ready or not self._dub_button.isChecked())
            self._play_button.setToolTip(
                self._tr("play") if self._play_button.isEnabled() else self._tr("status_waiting_dubbing_ready")
            )
        if message:
            self.statusBar().showMessage(message)
