from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_player.ui.task_center import collect_background_tasks, stop_background_tasks


class PlayerTaskCenterMixin:
    def _task_center_tab(self) -> QWidget:
        tab = QWidget()
        self._task_center_tab_widget = tab
        self._task_center_log: list[str] = getattr(self, "_task_center_log", [])
        self._task_center_retry_action: Callable[[], None] | None = None
        self._task_center_retry_label = ""

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(8)

        summary = QLabel(self._tr("task_center_summary"))
        summary.setProperty("i18n_key", "task_center_summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self._task_center_stop_button = self._make_button(
            "task_center_stop_all",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self._task_center_stop_button.clicked.connect(self._stop_task_center_tasks)
        self._task_center_retry_button = self._make_button(
            "task_center_retry",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._task_center_retry_button.clicked.connect(self._retry_task_center_action)
        self._task_center_refresh_button = self._make_button(
            "task_center_refresh",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._task_center_refresh_button.clicked.connect(self._refresh_task_center)
        toolbar_layout.addWidget(self._task_center_stop_button)
        toolbar_layout.addWidget(self._task_center_retry_button)
        toolbar_layout.addWidget(self._task_center_refresh_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        self._task_center_table = QTableWidget(0, 3)
        self._task_center_table.setHorizontalHeaderLabels(
            [
                self._tr("task_center_name"),
                self._tr("task_center_status"),
                self._tr("task_center_detail"),
            ]
        )
        self._task_center_table.verticalHeader().setVisible(False)
        self._task_center_table.setWordWrap(True)
        self._task_center_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._task_center_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._task_center_table.setColumnWidth(0, 150)
        self._task_center_table.setColumnWidth(1, 90)
        self._task_center_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._task_center_table, 2)

        layout.addWidget(self._section_title("task_center_log_title"))
        self._task_center_log_view = QPlainTextEdit()
        self._task_center_log_view.setReadOnly(True)
        self._task_center_log_view.setMaximumBlockCount(160)
        self._task_center_log_view.setMinimumHeight(120)
        self._task_center_log_view.setPlaceholderText(self._tr("task_center_log_empty"))
        self._task_center_log_view.setProperty("i18n_key", "task_center_log_empty")
        layout.addWidget(self._task_center_log_view, 1)

        self._refresh_task_center()
        return tab

    def _task_center_tab_changed(self, index: int) -> None:
        if hasattr(self, "_task_center_tab_widget") and self._settings_tab_contains(
            self._settings_tabs.widget(index), self._task_center_tab_widget
        ):
            self._refresh_task_center()

    def _refresh_task_center(self) -> None:
        if not hasattr(self, "_task_center_table"):
            return
        tasks = collect_background_tasks(self)
        self._task_center_table.setRowCount(len(tasks) or 1)
        if not tasks:
            self._set_task_center_row(0, self._tr("task_center_idle"), "", self._tr("runtime_tasks_idle"))
        else:
            for row, task in enumerate(tasks):
                self._set_task_center_row(row, task.name, task.status, task.detail)
        self._task_center_table.resizeRowsToContents()
        self._task_center_stop_button.setEnabled(bool(tasks))
        self._task_center_retry_button.setEnabled(self._task_center_retry_action is not None)
        retry_label = self._task_center_retry_label or self._tr("task_center_retry_unavailable")
        self._task_center_retry_button.setToolTip(retry_label)
        self._refresh_task_center_log()
        self._refresh_global_task_status(tasks)

    def _refresh_global_task_status(self, tasks=None) -> None:
        button = getattr(self, "_task_status_button", None)
        if button is None:
            return
        if tasks is None:
            tasks = collect_background_tasks(self)
        active = [task for task in tasks if task.status == "RUNNING"]
        if not active:
            button.setText(self._tr("task_status_idle"))
            button.setToolTip(self._tr("task_status_tooltip"))
            button.setProperty("activeTasks", "false")
        else:
            count = len(active)
            first = active[0]
            detail = " ".join(str(first.detail or "").split())
            if len(detail) > 72:
                detail = f"{detail[:69]}..."
            button.setText(self._tr("task_status_active").format(count=count))
            button.setToolTip(f"{first.name}: {detail}" if detail else first.name)
            button.setProperty("activeTasks", "true")
        button.style().unpolish(button)
        button.style().polish(button)

    def _set_task_center_row(self, row: int, name: str, status: str, detail: str) -> None:
        values = (name, status, detail)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value or ""))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._task_center_table.setItem(row, column, item)

    def _record_task_center_event(self, name: str, detail: object) -> None:
        text = " ".join(str(detail or "").split())
        if not text:
            return
        if not hasattr(self, "_task_center_log"):
            self._task_center_log = []
        entry = f"{name}: {text[:500]}"
        if not self._task_center_log or self._task_center_log[-1] != entry:
            self._task_center_log.append(entry)
            self._task_center_log = self._task_center_log[-80:]
        self._refresh_task_center()

    def _refresh_task_center_log(self) -> None:
        if not hasattr(self, "_task_center_log_view"):
            return
        self._task_center_log_view.setPlainText("\n".join(getattr(self, "_task_center_log", [])[-80:]))

    def _set_task_center_retry(self, label: str, action: Callable[[], None] | None) -> None:
        self._task_center_retry_label = str(label or "")
        self._task_center_retry_action = action
        self._refresh_task_center()

    def _retry_task_center_action(self) -> None:
        action = getattr(self, "_task_center_retry_action", None)
        if action is None:
            self.statusBar().showMessage(self._tr("task_center_retry_unavailable"))
            return
        action()
        self.statusBar().showMessage(self._tr("task_center_retry_started"))
        self._refresh_task_center()

    def _stop_task_center_tasks(self) -> None:
        summary = stop_background_tasks(self)
        self._refresh_task_center()
        self._refresh_runtime_tab()
        if summary.failed:
            message = self._tr("runtime_tasks_stop_partial").format(failed=", ".join(summary.failed))
        else:
            message = self._tr("runtime_tasks_stopped").format(count=summary.stopped)
        self.statusBar().showMessage(message)
