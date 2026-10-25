from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import UI_TEXT, UI_TEXT_ALIASES
from ai_player.ui.player_window_utils import ui_label as _ui_label


class PlayerUiFeature(Feature):
    _COMMAND_BUTTON_HEIGHT = 36
    _COMMAND_BUTTON_WIDTH = 112
    _COMMAND_BUTTON_MIN_WIDTH = 88
    _ICON_BUTTON_SIZE = 36

    _ICON_ALIASES = {
        "open": QStyle.StandardPixmap.SP_DirOpenIcon,
        "video": QStyle.StandardPixmap.SP_MediaPlay,
        "url": QStyle.StandardPixmap.SP_BrowserReload,
        "document": QStyle.StandardPixmap.SP_FileIcon,
        "meeting": QStyle.StandardPixmap.SP_MediaPlay,
        "export": QStyle.StandardPixmap.SP_DialogSaveButton,
        "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
        "reset": QStyle.StandardPixmap.SP_DialogResetButton,
        "help": QStyle.StandardPixmap.SP_DialogHelpButton,
        "stop": QStyle.StandardPixmap.SP_MediaStop,
        "retry": QStyle.StandardPixmap.SP_BrowserReload,
        "focus": QStyle.StandardPixmap.SP_TitleBarMaxButton,
    }

    def _i18n_text(self, key_or_text: str) -> str:
        language = self.context.config.gui_language
        if self.context.has("_ui_language_combo"):
            language = self.context.settings._ui_language()
        fallback = UI_TEXT.get("vi", {})
        strings = UI_TEXT.get(language, fallback)
        return strings.get(key_or_text, fallback.get(key_or_text, _ui_label(key_or_text)))

    def _app_icon(self, name: str | QStyle.StandardPixmap) -> QIcon:
        pixmap = name if isinstance(name, QStyle.StandardPixmap) else self.context.ui._ICON_ALIASES.get(str(name or ""))
        if pixmap is None:
            pixmap = QStyle.StandardPixmap.SP_FileIcon
        # Asking a widget wrapped by QStyleSheetStyle for a standard icon can
        # return a transparent pixmap on Windows (notably the panel arrows).
        # Render from a stable base style and tint the glyph with the theme's
        # text role so icon-only buttons always contrast with their surface.
        from ai_player.resources.themes.python_theme import values

        base_icon = QStyleFactory.create("Fusion").standardIcon(pixmap)
        color = QColor(values()["text"])
        icon = QIcon()
        for edge in (16, 20, 24, 32):
            source = base_icon.pixmap(QSize(edge, edge))
            if source.isNull():
                continue
            source_image = source.toImage()
            opaque = [
                (x, y)
                for y in range(source_image.height())
                for x in range(source_image.width())
                if source_image.pixelColor(x, y).alpha() > 0
            ]
            bounds = (
                QRect(
                    min(x for x, _y in opaque),
                    min(y for _x, y in opaque),
                    max(x for x, _y in opaque) - min(x for x, _y in opaque) + 1,
                    max(y for _x, y in opaque) - min(y for _x, y in opaque) + 1,
                )
                if opaque
                else QRect()
            )
            glyph = source.copy(bounds) if bounds.isValid() and not bounds.isEmpty() else source
            target_edge = max(12, edge - 4)
            glyph = glyph.scaled(
                target_edge,
                target_edge,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            tinted = QPixmap(QSize(edge, edge))
            tinted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(tinted)
            painter.drawPixmap((edge - glyph.width()) // 2, (edge - glyph.height()) // 2, glyph)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), color)
            painter.end()
            icon.addPixmap(tinted, QIcon.Mode.Normal, QIcon.State.Off)
        return icon if not icon.isNull() else base_icon

    def _make_button(self, text: str, icon: QIcon) -> QPushButton:
        label = self.context.ui._i18n_text(text)
        button = QPushButton(icon, label)
        key = text if text in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(text) or UI_TEXT_ALIASES.get(label)
        if key:
            button.setProperty("i18n_key", key)
            self.context.ui._set_control_tooltip(button, key)
        button.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
        button.setFixedWidth(self.context.ui._COMMAND_BUTTON_WIDTH)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _set_control_tooltip(self, widget: QWidget, key: str) -> None:
        tooltip = self.context.ui._i18n_text(key)
        widget.setToolTip(tooltip)
        widget.setProperty("i18n_tooltip_key", key)
        if isinstance(widget, QComboBox) and widget.isEditable() and widget.lineEdit() is not None:
            widget.lineEdit().setToolTip(tooltip)
            widget.lineEdit().setProperty("i18n_tooltip_key", key)

    @staticmethod
    def _compact_combo(combo: QComboBox) -> None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _option_combo(self, options: list[tuple[str, str]], current: str) -> QComboBox:
        combo = QComboBox()
        self.context.ui._compact_combo(combo)
        for label, value in options:
            combo.addItem(_ui_label(label), value)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    def _device_combo(self, devices: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        self.context.ui._compact_combo(combo)
        combo.setEditable(True)
        combo.addItem(self.context.ui._i18n_text("auto"), "")
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
        layout.addWidget(self.context.ui._field_label("source"), 0, 0)
        layout.addWidget(self.context.layout._audio_source_combo, 0, 1)
        layout.addWidget(self.context.ui._field_label("transcript"), 1, 0)
        layout.addWidget(self.context.ui._transcript_path_row(), 1, 1)
        self.context.sources._sync_audio_source_controls()
        return panel

    def _transcript_path_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.context.layout._transcript_path_edit, 1)
        layout.addWidget(self.context.layout._transcript_file_button)
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
        slider = self.context.ui._value_slider(minimum=minimum, maximum=maximum, step=step, value=value)
        label = self.context.ui._value_label(formatter(value))
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
    def _api_key_status_label() -> QLabel:
        label = QLabel("")
        label.setObjectName("apiKeyStatusLabel")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return label

    @staticmethod
    def _api_key_control(edit: QLineEdit, status_label: QLabel) -> QWidget:
        control = QWidget()
        layout = QVBoxLayout(control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(edit)
        layout.addWidget(status_label)
        return control

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
        label = self.context.ui._field_label(label_key)
        label.setObjectName("audioSliderLabel")
        label.setMinimumWidth(68)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.setObjectName("audioVolumeSlider")
        layout.addWidget(label)
        layout.addWidget(slider, 1)
        return control

    def _icon_button(self, icon: QStyle.StandardPixmap, tooltip: str) -> QPushButton:
        button = QPushButton(self.context.ui._app_icon(icon), "")
        button.setObjectName("toolButton")
        button.setToolTip(self.context.ui._i18n_text(tooltip))
        key = tooltip if tooltip in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(tooltip)
        if key:
            button.setProperty("i18n_tooltip_key", key)
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(self.context.ui._ICON_BUTTON_SIZE, self.context.ui._ICON_BUTTON_SIZE)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _field_label(self, text: str) -> QLabel:
        label_text = self.context.ui._i18n_text(text)
        label = QLabel(label_text)
        key = text if text in UI_TEXT.get("vi", {}) else UI_TEXT_ALIASES.get(text) or UI_TEXT_ALIASES.get(label_text)
        if key:
            label.setProperty("i18n_key", key)
        label.setObjectName("fieldLabel")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        return label

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(self.context.ui._i18n_text(text))
        if text in UI_TEXT.get("vi", {}):
            label.setProperty("i18n_key", text)
        label.setObjectName("sectionTitle")
        label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        return label

    def _apply_theme(self) -> None:
        from ai_player.resources.themes.python_theme import qt_stylesheet

        self.context.window.setStyleSheet(
            qt_stylesheet(
                """
            QMainWindow, QWidget#root {
                background: #ffffff;
                color: #172033;
                font-family: "Segoe UI Variable", "Segoe UI", "Arial";
                font-size: 9pt;
            }
            QFrame#sourceBar {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#headerActionGroup, QFrame#headerToolGroup {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#headerPrimaryGroup {
                background: transparent;
                border: 0;
            }
            QPushButton#taskStatusButton {
                background: #eef6f4;
                border: 1px solid #a8d6d0;
                border-radius: 14px;
                color: #0b514b;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 5px 8px;
            }
            QPushButton#taskStatusButton[activeTasks="true"] {
                background: #fff7e8;
                border-color: #e9b75d;
                color: #7a4b00;
            }
            QPushButton#taskStatusButton[activeTasks="error"] {
                background: #fff1f2;
                border-color: #f0a5af;
                color: #9f1239;
            }
            QFrame#taskDrawer {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#taskDrawer[activeTasks="true"] {
                background: #fff7e8;
                border-color: #e9b75d;
            }
            QFrame#taskDrawer[activeTasks="error"] {
                background: #fff1f2;
                border-color: #f0a5af;
            }
            QLabel#taskDrawerState {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 750;
                padding: 6px 8px;
            }
            QLabel#taskDrawerState[status="active"] {
                background: #fff7e8;
                border-color: #e9b75d;
                color: #7a4b00;
            }
            QLabel#taskDrawerState[status="error"] {
                background: #fff1f2;
                border-color: #e26d7a;
                color: #9f1239;
            }
            QLabel#taskDrawerSummary {
                color: #172033;
                font-size: 9pt;
                font-weight: 600;
            }
            QFrame#videoPanel {
                background: #f6f8fb;
                border: 1px solid #e7ecf2;
                border-radius: 8px;
            }
            QFrame#videoPanel[focusMedia="true"] {
                background: transparent;
                border: 0;
                border-radius: 0;
            }
            QFrame#sidePanel {
                background: #f8fafc;
                border: 1px solid #e1e7ef;
                border-radius: 8px;
            }
            QFrame#mediaFrame {
                background: #ffffff;
                border: 0;
                border-radius: 0;
            }
            QFrame#mediaFrame[focusMedia="true"] {
                border: 0;
                border-radius: 0;
            }
            QFrame#videoPlaceholder {
                background: #ffffff;
                border-radius: 0;
            }
            QFrame#videoPlaceholder[focusMedia="true"] {
                border-radius: 0;
            }
            QStackedWidget#mediaStack {
                background: #ffffff;
                border: 0;
                border-radius: 0;
            }
            QStackedWidget#mediaStack[focusMedia="true"] {
                border-radius: 0;
            }
            QScrollArea#sideScroll {
                background: #ffffff;
                border: 0;
            }
            QScrollArea#sideScroll QWidget#qt_scrollarea_viewport,
            QScrollArea#sideScroll QWidget[settingsPage="true"] {
                background: #ffffff;
                color: #172033;
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
            QLabel#runtimeValue {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                color: #172033;
                padding: 6px 8px;
            }
            QLabel#presetInspector {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                color: #56657a;
                font-size: 8.5pt;
                padding: 7px 9px;
            }
            QPushButton#presetCardButton {
                background: #ffffff;
                border: 1px solid #d5dde8;
                border-radius: 8px;
                color: #172033;
                font-size: 8.3pt;
                font-weight: 650;
                padding: 7px 8px;
                text-align: left;
            }
            QPushButton#presetCardButton:hover {
                background: #f7fbfa;
                border-color: #8bbdb6;
            }
            QPushButton#workflowCardButton,
            QPushButton#readinessActionButton {
                text-align: left;
                padding: 7px 10px;
            }
            QPushButton#readinessActionButton {
                background: #ffffff;
                border-color: #d5dde8;
            }
            QPushButton#readinessActionButton:hover {
                background: #f2f7ff;
                border-color: #7da2df;
                color: #19479f;
            }
            QPushButton#readinessActionButton:pressed {
                background: #e6edff;
                border-color: #2459c4;
            }
            QPushButton#presetCardButton:checked {
                background: #e6f3f1;
                border-color: #146c63;
                color: #0b514b;
            }
            QScrollArea#mediaStartScroll {
                background: #ffffff;
                border: 0;
            }
            QScrollArea#mediaStartScroll QWidget#qt_scrollarea_viewport {
                background: #ffffff;
            }
            QFrame#mediaStartPanel {
                background: #ffffff;
                border: 0;
                border-radius: 0;
            }
            QLabel#mediaStartTitle {
                color: #101828;
                font-size: 14.5pt;
                font-weight: 750;
            }
            QLabel#mediaStartSubtitle {
                color: #667085;
                font-size: 9pt;
            }
            QFrame#mediaStartQuickPanel {
                background: transparent;
                border: 0;
            }
            QFrame#mediaStartDropZone, QFrame#mediaStartInfoPanel {
                background: #f8fafc;
                border: 1px solid #dbe2ea;
                border-radius: 8px;
            }
            QFrame#mediaStartDropZone {
                background: #fbfefd;
                border-style: dashed;
                border-color: #9bc9c3;
            }
            QLabel#mediaStartDropTitle, QLabel#mediaStartSectionTitle {
                color: #101828;
                font-size: 9.2pt;
                font-weight: 750;
            }
            QLabel#mediaStartDropDetail, QLabel#mediaStartMutedText, QLabel#mediaStartConfigSummary {
                color: #56657a;
                font-size: 8.4pt;
            }
            QLineEdit#mediaStartQuickSourceEdit {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #172033;
                padding: 5px 8px;
            }
            QPushButton#mediaStartQuickOpenButton {
                background: #146c63;
                border-color: #146c63;
                color: #ffffff;
                font-weight: 700;
                padding: 6px 9px;
            }
            QPushButton#mediaStartQuickOpenButton:hover {
                background: #0f5f57;
                border-color: #0f5f57;
                color: #ffffff;
            }
            QPushButton#mediaStartRecentButton {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #172033;
                font-size: 8.2pt;
                font-weight: 600;
                padding: 4px 8px;
                text-align: left;
            }
            QPushButton#mediaStartRecentButton:hover {
                background: #eef6f4;
                border-color: #6fa79f;
                color: #0b514b;
            }
            QPushButton#mediaStartSetupTitle {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 650;
                padding: 5px 8px;
            }
            QPushButton#mediaStartWorkflowButton {
                background: #f7f9fb;
                border-color: #c6d0dc;
                color: #172033;
                font-weight: 600;
                padding: 10px 12px;
                text-align: left;
            }
            QPushButton#mediaStartWorkflowButton:hover {
                background: #eef6f4;
                border-color: #6fa79f;
                color: #0b514b;
            }
            QFrame#mediaStartWorkflowCard {
                background: #ffffff;
                border: 1px solid #dbe2ea;
                border-radius: 8px;
            }
            QFrame#mediaStartWorkflowCard:hover {
                border-color: #9bc9c3;
                background: #fbfefd;
            }
            QLabel#mediaStartWorkflowIcon {
                background: #f0f7f6;
                border: 1px solid #c9e3df;
                border-radius: 8px;
                padding: 5px;
            }
            QLabel#mediaStartWorkflowTitle {
                color: #101828;
                font-size: 10.2pt;
                font-weight: 750;
            }
            QLabel#mediaStartWorkflowDetail {
                color: #56657a;
                font-size: 8.5pt;
            }
            QLabel#mediaStartWorkflowRuntime {
                background: #f2faf8;
                border: 1px solid #cfe7e3;
                border-radius: 9px;
                color: #0b514b;
                font-size: 8pt;
                font-weight: 650;
                padding: 3px 8px;
            }
            QWidget#workflowCardActions {
                background: transparent;
                border: 0;
            }
            QPushButton#workflowCardPrimaryButton {
                background: #146c63;
                border-color: #146c63;
                color: #ffffff;
                font-weight: 700;
                padding: 6px 9px;
            }
            QPushButton#workflowCardPrimaryButton:hover {
                background: #0f5f57;
                border-color: #0f5f57;
                color: #ffffff;
            }
            QPushButton#workflowCardSecondaryButton {
                background: #ffffff;
                border-color: #c6d0dc;
                color: #56657a;
                font-size: 8.3pt;
                font-weight: 600;
                padding: 5px 7px;
            }
            QPushButton#workflowCardSecondaryButton:hover {
                background: #f7f9fb;
                border-color: #8c99aa;
                color: #172033;
            }
            QPushButton#mediaStartProfileButton {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 5px 8px;
            }
            QPushButton#mediaStartProfileButton:hover {
                background: #f7f9fb;
                border-color: #8c99aa;
                color: #172033;
            }
            QPushButton#mediaStartProfileButton:checked {
                background: #e6f3f1;
                border-color: #146c63;
                color: #0b514b;
            }
            QPushButton#workflowCardButton {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                color: #172033;
                font-weight: 600;
                padding: 8px 10px;
                text-align: left;
            }
            QPushButton#workflowCardButton:hover {
                background: #eef6f4;
                border-color: #6fa79f;
                color: #0b514b;
            }
            QFrame#telegramChannelView, QWidget#telegramChannelSidePanel {
                background: #ffffff;
            }
            QListWidget#telegramChannelList {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                outline: 0;
                alternate-background-color: #f8fafc;
            }
            QListWidget#telegramChannelList::item {
                color: #172033;
                background: transparent;
                border: 2px solid transparent;
                border-radius: 7px;
                padding: 6px 8px;
                margin: 2px;
            }
            QListWidget#telegramChannelList::item:selected,
            QListWidget#telegramChannelList::item:selected:active,
            QListWidget#telegramChannelList::item:selected:!active {
                color: #172033;
                background: transparent;
                border: 2px solid #0b76d1;
            }
            QListWidget#telegramChannelList::item:hover {
                border-color: #8fbce8;
            }
            QFrame#controls {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#displayOptionsPanel {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#panelVisibilityBar {
                background: transparent;
                border: 0;
            }
            QTextEdit#transcript {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                padding: 10px;
                selection-background-color: #146c63;
            }
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                color: #172033;
                border: 1px solid #d8dee7;
                gridline-color: #e1e7ef;
                selection-background-color: #e6f3f1;
                selection-color: #172033;
            }
            QTableWidget::item {
                background: #ffffff;
                color: #172033;
                padding: 5px;
            }
            QTableWidget::item:selected {
                background: #e6f3f1;
                color: #0b514b;
            }
            QHeaderView::section {
                background: #eef2f6;
                color: #172033;
                border: 0;
                border-right: 1px solid #d8dee7;
                border-bottom: 1px solid #d8dee7;
                padding: 5px;
                font-weight: 600;
            }
            QTableCornerButton::section {
                background: #eef2f6;
                border: 0;
                border-right: 1px solid #d8dee7;
                border-bottom: 1px solid #d8dee7;
            }
            QTableWidget#transcriptSegmentTable {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
                gridline-color: #e7ecf2;
                selection-background-color: #e6f3f1;
                selection-color: #172033;
            }
            QTableWidget#transcriptSegmentTable::item {
                padding: 5px;
            }
            QLabel#inlineBanner {
                background: #fff8e6;
                border: 1px solid #e9c46a;
                border-radius: 8px;
                color: #604300;
                padding: 7px 9px;
                font-weight: 600;
            }
            QFrame#transcriptStatusStrip {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QLabel#transcriptStatusPill {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 650;
                padding: 6px 8px;
            }
            QLabel#transcriptStatusPill[status="ok"] {
                border-color: #9ed3bd;
                color: #145338;
            }
            QLabel#transcriptStatusPill[status="warn"] {
                border-color: #e9b75d;
                color: #7a4b00;
            }
            QLabel#transcriptStatusPill[status="muted"] {
                color: #56657a;
            }
            QFrame#nextActionPanel, QFrame#transcriptEmptyPanel {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#transcriptEmptyPanel {
                background: #ffffff;
            }
            QLabel#nextActionTitle {
                color: #101828;
                font-size: 10pt;
                font-weight: 750;
            }
            QLabel#nextActionDetail {
                color: #56657a;
                font-size: 8.5pt;
            }
            QLabel#nextActionStepMarker {
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                color: #64748b;
                font-size: 8pt;
                font-weight: 800;
                padding: 2px 0;
                qproperty-alignment: AlignCenter;
            }
            QLabel#nextActionStepMarker[status="done"] {
                background: #e8f4ee;
                border-color: #9ed3bd;
                color: #145338;
            }
            QLabel#nextActionStepMarker[status="active"] {
                background: #e6f3f1;
                border-color: #146c63;
                color: #0b514b;
            }
            QLabel#nextActionStepMarker[status="warn"] {
                background: #fff7e8;
                border-color: #e9b75d;
                color: #7a4b00;
            }
            QLabel#nextActionStep {
                color: #56657a;
                font-size: 8.4pt;
                font-weight: 600;
            }
            QLabel#nextActionStep[status="done"] {
                color: #145338;
            }
            QLabel#nextActionStep[status="active"] {
                color: #0b514b;
            }
            QLabel#nextActionStep[status="warn"] {
                color: #7a4b00;
            }
            QPushButton#nextActionButton, QPushButton#nextActionPrimaryButton {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #172033;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 5px 7px;
            }
            QPushButton#nextActionPrimaryButton {
                background: #146c63;
                border-color: #146c63;
                color: #ffffff;
                font-size: 9pt;
                padding: 7px 10px;
            }
            QPushButton#nextActionButton:hover, QPushButton#nextActionPrimaryButton:hover {
                background: #eef6f4;
                border-color: #6fa79f;
                color: #0b514b;
            }
            QFrame#transcriptSegmentEditor {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QPushButton#transcriptSegmentButton {
                min-height: 30px;
                padding: 6px 8px;
                font-size: 8.5pt;
            }
            QPushButton#transcriptFilterButton, QPushButton#transcriptBatchButton {
                background: #ffffff;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                color: #56657a;
                font-size: 8.3pt;
                font-weight: 650;
                padding: 5px 7px;
            }
            QPushButton#transcriptFilterButton:hover, QPushButton#transcriptBatchButton:hover {
                background: #f7f9fb;
                border-color: #8c99aa;
                color: #172033;
            }
            QPushButton#transcriptFilterButton:checked {
                background: #e6f3f1;
                border-color: #146c63;
                color: #0b514b;
            }
            QTextEdit#transcriptSegmentSource,
            QTextEdit#transcriptSegmentTarget {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                padding: 6px;
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
            QFrame#settingsNav {
                background: #eef2f6;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QPushButton#settingsNavButton {
                background: transparent;
                border: 0;
                border-radius: 6px;
                color: #56657a;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 5px 6px;
            }
            QPushButton#settingsNavButton:hover {
                background: #ffffff;
                color: #146c63;
            }
            QPushButton#settingsNavButton:checked {
                background: #ffffff;
                color: #0b514b;
            }
            QFrame#modelStatusStrip {
                background: #f7f9fb;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QFrame#settingsSectionCard {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 8px;
            }
            QToolButton#settingsSectionToggle {
                color: #146c63;
                border: 0;
                padding: 2px;
            }
            QLabel#modelStatusPill {
                background: #ffffff;
                border: 1px solid #d8dee7;
                border-radius: 7px;
                color: #172033;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 6px 8px;
            }
            QLabel#modelStatusPill[status="ok"] {
                border-color: #9ed3bd;
                color: #145338;
            }
            QLabel#modelStatusPill[status="warn"] {
                border-color: #e9b75d;
                color: #7a4b00;
            }
            QLabel#modelStatusPill[status="muted"] {
                color: #56657a;
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
                color: #172033;
                border: 1px solid #c6d0dc;
                border-radius: 7px;
                padding: 5px 9px;
                min-height: 22px;
                placeholder-text-color: #667085;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #172033;
                border: 1px solid #c6d0dc;
                selection-background-color: #e6edff;
                selection-color: #172033;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                background: #ffffff;
                color: #172033;
                min-height: 28px;
                padding: 5px 8px;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #e6edff;
                color: #172033;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #8c99aa;
            }
            QComboBox:focus, QLineEdit:focus {
                border-color: #146c63;
            }
            QComboBox:disabled, QLineEdit:disabled {
                color: #64748b;
                background: #ffffff;
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
                background: #ffffff;
                color: #56657a;
                border-top: 1px solid #d8dee7;
            }
            """
            )
        )

    def _set_dubbing_ready(self, ready: bool, message: str = "") -> None:
        self.context.media.playback.dubbing_ready = ready
        if self.context.has("_play_button"):
            self.context.layout._play_button.setEnabled(ready or not self.context.layout._dub_button.isChecked())
            self.context.layout._play_button.setToolTip(
                self.context.settings._tr("play")
                if self.context.layout._play_button.isEnabled()
                else self.context.settings._tr("status_waiting_dubbing_ready")
            )
        if message:
            self.context.window.statusBar().showMessage(message)
