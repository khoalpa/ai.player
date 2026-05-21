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
        button.setMinimumHeight(32)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @staticmethod
    def _compact_combo(combo: QComboBox) -> None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
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
        combo.addItem(self._i18n_text("auto"), "")
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

    def _audio_slider_control(self, label_key: str, slider: QSlider) -> QWidget:
        control = QWidget()
        control.setObjectName("audioSliderControl")
        control.setMaximumWidth(300)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(control)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        label = self._field_label(label_key)
        label.setObjectName("audioSliderLabel")
        label.setMinimumWidth(68)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.setObjectName("audioVolumeSlider")
        layout.addWidget(label)
        layout.addWidget(slider, 1)
        return control

    def _icon_button(self, icon: QStyle.StandardPixmap, tooltip: str) -> QPushButton:
        button = QPushButton(self.style().standardIcon(icon), "")
        button.setObjectName("toolButton")
        button.setToolTip(self._i18n_text(tooltip))
        key = tooltip if tooltip in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(tooltip)
        if key:
            button.setProperty("i18n_tooltip_key", key)
        button.setFixedSize(32, 32)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _field_label(self, text: str) -> QLabel:
        label_text = self._i18n_text(text)
        label = QLabel(label_text)
        key = text if text in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(text) or UI_TEXT_ALIASES.get(label_text)
        if key:
            label.setProperty("i18n_key", key)
        label.setObjectName("fieldLabel")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
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
                background: #f4f6f8;
                color: #172033;
                font-family: "Segoe UI Variable", "Segoe UI", "Arial";
                font-size: 9pt;
            }
            QFrame#sourceBar {
                background: #fbfcfd;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#videoPanel {
                background: #fbfcfd;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#sidePanel {
                background: #fbfcfd;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#mediaFrame {
                background: #0b1020;
                border: 1px solid #111827;
                border-radius: 8px;
            }
            QFrame#videoPlaceholder {
                background: #0b1020;
                border-radius: 8px;
            }
            QStackedWidget#mediaStack {
                background: #0b1020;
                border-radius: 8px;
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
            QScrollArea#sideScroll {
                background: transparent;
                border: 0;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 4px 1px 4px 1px;
            }
            QScrollBar::handle:vertical {
                background: #b9c3d0;
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8796a8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QSplitter::handle {
                background: transparent;
            }
            QSplitter::handle:horizontal {
                width: 8px;
            }
            QLabel#appTitle {
                color: #101828;
                font-size: 16pt;
                font-weight: 750;
            }
            QLabel#sourceLabel {
                color: #667085;
                padding-left: 10px;
            }
            QLabel#sectionTitle {
                color: #146c63;
                padding-top: 8px;
                padding-bottom: 2px;
            }
            QLabel#fieldLabel {
                color: #56657a;
                font-size: 8.5pt;
            }
            QLabel#valueLabel {
                color: #172033;
                font-size: 8.5pt;
            }
            QVideoWidget#videoSurface {
                background: #0b1020;
                border-radius: 8px;
            }
            QFrame#controls {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QTextEdit#transcript {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                padding: 10px;
                selection-background-color: #146c63;
            }
            QTextEdit#documentView {
                background: #ffffff;
                color: #172033;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                padding: 24px;
                font-size: 15pt;
                line-height: 1.45;
                selection-background-color: #146c63;
            }
            QTabWidget#settingsTabs::pane {
                border: 1px solid #d8dee7;
                border-radius: 8px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #eef2f6;
                color: #56657a;
                border: 1px solid #d8dee7;
                border-bottom: 0;
                padding: 7px 11px;
                margin-right: 3px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                min-width: 58px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #146c63;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #ffffff;
                color: #146c63;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                padding: 5px 10px;
                color: #172033;
            }
            QPushButton:hover {
                background: #f7f9fb;
                border-color: #8c99aa;
            }
            QPushButton:pressed, QPushButton:checked {
                background: #e6f3f1;
                border-color: #146c63;
                color: #0b514b;
            }
            QPushButton#toolButton {
                background: #ffffff;
                border-color: #c6d0dc;
                padding: 0;
            }
            QPushButton#toolButton:hover {
                background: #f1f4f8;
                border-color: #8c99aa;
            }
            QPushButton#sourceButton {
                background: #f7f9fb;
                border-color: #c6d0dc;
                color: #172033;
                font-weight: 600;
            }
            QPushButton#sourceButton:hover {
                background: #eef6f4;
                border-color: #6fa79f;
                color: #0b514b;
            }
            QPushButton#primaryButton {
                background: #146c63;
                border-color: #146c63;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: #0f5f57;
                border-color: #0f5f57;
            }
            QPushButton#dubButton:checked {
                background: #e8f4ee;
                border-color: #237a57;
                color: #145338;
                font-weight: 600;
            }
            QComboBox, QLineEdit {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                padding: 5px 9px;
                min-height: 22px;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #8c99aa;
            }
            QComboBox:focus, QLineEdit:focus {
                border-color: #146c63;
            }
            QComboBox:disabled, QLineEdit:disabled {
                color: #8a96a6;
                background: #f4f6f8;
            }
            QCheckBox {
                color: #172033;
                spacing: 7px;
                padding: 3px 0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:checked {
                background: #146c63;
                border: 1px solid #146c63;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                background: #ffffff;
                border: 1px solid #91a2b4;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked:hover {
                border-color: #146c63;
            }
            QWidget#audioSliderControl {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 7px;
            }
            QLabel#audioSliderLabel {
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 600;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #dce3ec;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: #146c63;
            }
            QSlider::handle:horizontal:hover {
                background: #0f5f57;
            }
            QLabel#timeLabel {
                color: #172033;
                font-weight: 600;
            }
            QStatusBar {
                background: #f4f6f8;
                color: #56657a;
                border-top: 1px solid #d8dee7;
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
