from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QStyle, QVBoxLayout, QWidget


class PlayerRuntimeMixin:
    def _runtime_tab(self) -> QWidget:
        tab = QWidget()
        self._runtime_tab_widget = tab
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(8)

        summary = QLabel(self._tr("runtime_summary"))
        summary.setProperty("i18n_key", "runtime_summary")
        summary.setObjectName("runtimeSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        warmup_grid = QGridLayout()
        warmup_grid.setHorizontalSpacing(8)
        warmup_grid.setVerticalSpacing(4)
        warmup_grid.addWidget(self._section_title("runtime_warmup_group"), 0, 0, 1, 2)
        warmup_grid.addWidget(self._runtime_warmup_enabled_check, 1, 0, 1, 2)
        warmup_grid.addWidget(self._runtime_warmup_whisper_check, 2, 0)
        warmup_grid.addWidget(self._runtime_warmup_translation_check, 2, 1)
        warmup_grid.addWidget(self._runtime_warmup_tts_check, 3, 0, 1, 2)
        layout.addLayout(warmup_grid)

        task_toolbar = QWidget()
        task_toolbar_layout = QHBoxLayout(task_toolbar)
        task_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self._runtime_stop_tasks_button = self._make_button(
            "runtime_tasks_stop",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self._sync_runtime_stop_tasks_button_width()
        self._runtime_stop_tasks_button.clicked.connect(self._stop_runtime_background_tasks)
        self._runtime_stop_tasks_button.setEnabled(False)
        task_toolbar_layout.addWidget(self._runtime_stop_tasks_button)
        task_toolbar_layout.addStretch(1)
        layout.addWidget(task_toolbar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        self._runtime_labels: dict[str, QLabel] = {}
        rows = [
            ("health", "runtime_health"),
            ("privacy", "runtime_privacy"),
            ("tasks", "runtime_tasks"),
            ("media", "runtime_media"),
            ("gpu_runtime", "runtime_gpu_runtime"),
            ("process_cpu", "runtime_process_cpu"),
            ("process_memory", "runtime_process_memory"),
            ("system_cpu", "runtime_system_cpu"),
            ("system_memory", "runtime_system_memory"),
            ("gpu", "runtime_gpu"),
            ("python", "runtime_python"),
            ("platform", "runtime_platform"),
            ("pid", "runtime_pid"),
            ("diagnostics", "runtime_diagnostics"),
        ]
        for row, (key, title) in enumerate(rows):
            title_label = self._field_label(title)
            value_label = QLabel("...")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            self._runtime_labels[key] = value_label
            grid.addWidget(title_label, row, 0)
            grid.addWidget(value_label, row, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        self._runtime_tab_controller.bind(
            labels=self._runtime_labels,
            stop_tasks_button=self._runtime_stop_tasks_button,
            tab_widget=tab,
        )
        return tab

    def _sync_runtime_stop_tasks_button_width(self) -> None:
        button = getattr(self, "_runtime_stop_tasks_button", None)
        if button is None:
            return
        button.setMaximumWidth(16777215)
        button.setMinimumWidth(0)
        width = max(self._COMMAND_BUTTON_WIDTH, button.sizeHint().width() + 12)
        button.setFixedWidth(width)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _refresh_runtime_tab(self) -> None:
        self._runtime_tab_controller.refresh()

    def _runtime_tab_changed(self, index: int) -> None:
        self._runtime_tab_controller.tab_changed(index)

    @staticmethod
    def _settings_tab_contains(tab: QWidget | None, content: QWidget) -> bool:
        return tab is content or (hasattr(tab, "widget") and tab.widget() is content)

    def _runtime_media_info_text_current(self, force: bool = False) -> str:
        return self._runtime_tab_controller.media_info_text_current(force=force)

    def _document_runtime_info(self) -> str:
        return self._runtime_tab_controller.document_runtime_info()

    def _probe_media_info(self, source_path: str) -> str:
        return self._runtime_tab_controller.probe_media_info(source_path)

    def _format_media_probe(self, path: Path, data: dict) -> str:
        return self._runtime_tab_controller.format_media_probe(path, data)

    def _system_cpu_percent(self) -> float | None:
        return self._runtime_tab_controller.system_cpu_percent()

    def _read_system_cpu_times(self) -> tuple[int, int] | None:
        return self._runtime_tab_controller.read_system_cpu_times()

    def _process_memory_bytes(self) -> int | None:
        return self._runtime_tab_controller.process_memory_bytes()

    def _system_memory(self) -> tuple[int, int, float] | None:
        return self._runtime_tab_controller.system_memory()

    def _gpu_status_text(self) -> str:
        return self._runtime_tab_controller.gpu_status_text()

    def _gpu_runtime_text(self) -> str:
        return self._runtime_tab_controller.gpu_runtime_text()

    def _runtime_diagnostics_summary(self) -> str:
        return self._runtime_tab_controller.diagnostics_summary()

    def _runtime_health_summary(self) -> str:
        return self._runtime_tab_controller.health_summary()

    def _runtime_privacy_summary(self) -> str:
        return self._runtime_tab_controller.privacy_summary()

    def _runtime_task_summary(self, tasks: tuple[object, ...] | None = None) -> str:
        return self._runtime_tab_controller.task_summary(tasks)

    def _set_background_task_detail(self, name: str, detail: object, *, log_detail: object | None = None) -> None:
        controller = getattr(self, "_background_task_controller", None)
        if controller is None:
            return
        controller.set_detail(name, detail, log_detail=log_detail)

    def _clear_background_task_detail(self, name: str) -> None:
        controller = getattr(self, "_background_task_controller", None)
        if controller is None:
            return
        controller.clear_detail(name)

    def _stop_runtime_background_tasks(self) -> None:
        self._runtime_tab_controller.stop_background_tasks()

    def _format_seconds(self, value: float | None) -> str:
        if value is None:
            return self._tr("runtime_unknown")
        try:
            seconds = float(value)
        except (OverflowError, TypeError, ValueError):
            return self._tr("runtime_unknown")
        if not math.isfinite(seconds):
            return self._tr("runtime_unknown")
        seconds_total = max(0, int(round(seconds)))
        hours, remainder = divmod(seconds_total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _format_bytes(self, value: int) -> str:
        try:
            amount = float(value)
        except (OverflowError, TypeError, ValueError):
            return self._tr("runtime_unknown")
        if not math.isfinite(amount):
            return self._tr("runtime_unknown")
        amount = max(0.0, amount)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
            amount /= 1024
        return f"{amount:.1f} TB"
