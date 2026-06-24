from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_player.core.config import PROJECT_ROOT, RUNTIME_DIR
from ai_player.services.asr import asr_transcript_cache_stats, clear_asr_transcript_cache
from ai_player.services.tts_base import clear_tts_cache, tts_cache_stats
from ai_player.services.workflow_cache import clear_workflow_text_cache, workflow_text_cache_stats
from ai_player.ui.task_center import BackgroundTask, collect_background_tasks, stop_background_tasks


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
        info_tasks = self._task_center_info_tasks()
        rows = self._task_center_rows(tasks, info_tasks)
        self._task_center_table.setRowCount(len(rows) or 1)
        if not rows:
            self._set_task_center_row(0, self._tr("task_center_idle"), "", self._tr("runtime_tasks_idle"))
        else:
            for row, task in enumerate(rows):
                self._set_task_center_row(row, task.name, task.status, task.detail)
        self._task_center_table.resizeRowsToContents()
        self._task_center_stop_button.setEnabled(bool(tasks))
        self._task_center_retry_button.setEnabled(self._task_center_retry_action is not None)
        retry_label = self._task_center_retry_label or self._tr("task_center_retry_unavailable")
        self._task_center_retry_button.setToolTip(retry_label)
        self._refresh_task_center_log()
        self._refresh_global_task_status(tasks)
        if hasattr(self, "_refresh_next_action_panel"):
            self._refresh_next_action_panel()

    def _task_center_rows(
        self,
        tasks: tuple[BackgroundTask, ...],
        info_tasks: tuple[BackgroundTask, ...],
    ) -> tuple[BackgroundTask, ...]:
        rows: list[BackgroundTask] = []
        if tasks:
            rows.append(BackgroundTask(self._tr("task_center_group_running"), "", ""))
            for task in tasks:
                rows.extend(self._task_timeline_rows(task))
        if info_tasks:
            rows.append(BackgroundTask(self._tr("task_center_group_cache"), "", ""))
            rows.extend(info_tasks)
            cache_hit = self._cache_hit_task()
            if cache_hit is not None:
                rows.append(cache_hit)
        last_error = str(getattr(self, "_task_center_last_error", "") or "").strip()
        if last_error:
            rows.append(BackgroundTask(self._tr("task_center_group_errors"), "", ""))
            rows.append(BackgroundTask(self._tr("task_center_last_error"), self._tr("task_status_error"), last_error))
        return tuple(rows)

    def _task_timeline_rows(self, task: BackgroundTask) -> tuple[BackgroundTask, ...]:
        return (
            BackgroundTask(task.name, self._tr("task_center_timeline_prepare"), self._tr("task_center_timeline_ready")),
            BackgroundTask(task.name, self._tr("task_center_timeline_process"), task.detail),
            BackgroundTask(task.name, self._tr("task_center_timeline_done"), self._tr("task_center_timeline_pending")),
        )

    def _cache_hit_task(self) -> BackgroundTask | None:
        asr = asr_transcript_cache_stats()
        text = workflow_text_cache_stats()
        tts = tts_cache_stats()
        hits = int(asr.get("hits", 0)) + int(text.get("hits", 0)) + int(tts.get("hits", 0))
        if hits <= 0:
            return None
        return BackgroundTask(
            self._tr("task_center_cache_hit"),
            self._tr("task_center_timeline_done"),
            self._tr("task_center_cache_hit_detail").format(count=hits),
        )

    def _task_center_info_tasks(self) -> tuple[BackgroundTask, ...]:
        detail = self._workflow_cache_summary()
        if not detail:
            return ()
        return (
            BackgroundTask(
                self._tr("task_center_cache_name"),
                self._tr("task_center_cache_status"),
                detail,
            ),
        )

    def _workflow_cache_summary(self) -> str:
        asr = asr_transcript_cache_stats()
        text = workflow_text_cache_stats()
        tts = tts_cache_stats()
        total_activity = sum(
            int(stats.get(key, 0))
            for stats in (asr, text, tts)
            for key in ("hits", "misses", "writes", "entries")
        ) + int(getattr(self, "_url_cache_completed_count", 0) or 0)
        if total_activity <= 0:
            return ""
        return self._tr("task_center_cache_detail").format(
            asr_hits=asr.get("hits", 0),
            asr_writes=asr.get("writes", 0),
            text_hits=text.get("hits", 0),
            text_writes=text.get("writes", 0),
            tts_hits=tts.get("hits", 0),
            tts_writes=tts.get("writes", 0),
            url_cached=int(getattr(self, "_url_cache_completed_count", 0) or 0),
            entries=asr.get("entries", 0) + text.get("entries", 0) + tts.get("entries", 0),
        )

    def _refresh_global_task_status(self, tasks=None) -> None:
        button = getattr(self, "_task_status_button", None)
        if button is None:
            return
        if tasks is None:
            tasks = collect_background_tasks(self)
        active = [task for task in tasks if task.status == "RUNNING"]
        if not active:
            has_error = getattr(self, "_task_center_retry_action", None) is not None
            button.setText(self._tr("task_status_error" if has_error else "task_status_idle"))
            button.setToolTip(self._tr("task_status_tooltip"))
            button.setProperty("activeTasks", "error" if has_error else "false")
            self._refresh_task_drawer_summary(self._tr("task_drawer_idle"), active=False)
        else:
            count = len(active)
            first = active[0]
            detail = " ".join(str(first.detail or "").split())
            if len(detail) > 72:
                detail = f"{detail[:69]}..."
            button.setText(self._tr("task_status_active"))
            button.setToolTip(f"{first.name}: {detail}" if detail else first.name)
            button.setProperty("activeTasks", "true")
            summary = self._tr("task_drawer_running").format(
                count=count,
                task=first.name,
                detail=detail or first.status,
            )
            self._refresh_task_drawer_summary(summary, active=True)
        button.style().unpolish(button)
        button.style().polish(button)

    def _refresh_task_drawer_summary(self, text: str, *, active: bool) -> None:
        drawer = getattr(self, "_task_drawer", None)
        if drawer is not None:
            drawer.setProperty("activeTasks", "true" if active else "false")
            style = drawer.style()
            style.unpolish(drawer)
            style.polish(drawer)
            if active:
                self._task_drawer_user_open = False
                drawer.setVisible(not self._task_drawer_hidden_for_video_playback())
            elif not getattr(self, "_task_drawer_user_open", False):
                drawer.hide()
        summary = getattr(self, "_task_drawer_summary", None)
        if summary is not None:
            summary.setText(text)
            summary.setProperty("i18n_key", "task_drawer_idle" if not active else "")
        stop_button = getattr(self, "_task_drawer_stop_button", None)
        if stop_button is not None:
            stop_button.setEnabled(active)
        retry_button = getattr(self, "_task_drawer_retry_button", None)
        if retry_button is not None:
            retry_button.setEnabled(getattr(self, "_task_center_retry_action", None) is not None)

    def _task_drawer_hidden_for_video_playback(self) -> bool:
        if getattr(self, "_document_mode", False):
            return False
        player = getattr(self, "_player", None)
        is_playing = getattr(player, "is_playing", None)
        return bool(callable(is_playing) and is_playing())

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
        if action is not None and self._task_center_retry_label:
            self._task_center_last_error = self._task_center_retry_label
        self._refresh_task_center()

    def _clear_workflow_caches(self) -> None:
        clear_asr_transcript_cache()
        clear_workflow_text_cache()
        clear_tts_cache()
        self._url_cache_completed_count = 0
        self._task_center_last_error = ""
        self._record_task_center_event(self._tr("task_center_cache_name"), self._tr("task_center_cache_cleared"))
        self.statusBar().showMessage(self._tr("task_center_cache_cleared"))
        self._refresh_task_center()

    def _show_cache_inspector(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr("cache_inspector_title"))
        layout = QVBoxLayout(dialog)
        table = QTableWidget(3, 4, dialog)
        table.setHorizontalHeaderLabels(
            [
                self._tr("cache_inspector_cache"),
                self._tr("cache_inspector_entries"),
                self._tr("cache_inspector_size"),
                self._tr("cache_inspector_activity"),
            ]
        )
        rows = self._cache_inspector_rows()
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        layout.addWidget(table)

        buttons = QWidget(dialog)
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        for label_key, callback in (
            ("cache_inspector_clear_asr", self._clear_asr_cache_only),
            ("cache_inspector_clear_text", self._clear_text_cache_only),
            ("cache_inspector_clear_tts", self._clear_tts_cache_only),
            ("cache_inspector_clear_all", self._clear_workflow_caches),
        ):
            button = QPushButton(self._tr(label_key), dialog)
            button.clicked.connect(callback)
            button.clicked.connect(dialog.accept)
            button_layout.addWidget(button)
        layout.addWidget(buttons)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.resize(640, 300)
        dialog.exec()

    def _cache_inspector_rows(self) -> list[tuple[str, int, str, str]]:
        asr = asr_transcript_cache_stats()
        text = workflow_text_cache_stats()
        tts = tts_cache_stats()
        return [
            self._cache_inspector_row("ASR", asr, RUNTIME_DIR / "asr-cache"),
            self._cache_inspector_row("Text", text, None),
            self._cache_inspector_row("TTS", tts, RUNTIME_DIR / "tts-cache"),
        ]

    def _cache_inspector_row(self, name: str, stats: dict[str, int], path) -> tuple[str, int, str, str]:
        return (
            name,
            int(stats.get("entries", 0)),
            self._format_bytes(self._cache_dir_size(path)) if path is not None else "-",
            self._tr("cache_inspector_activity").format(
                hits=stats.get("hits", 0),
                misses=stats.get("misses", 0),
                writes=stats.get("writes", 0),
            ),
        )

    @staticmethod
    def _cache_dir_size(path) -> int:
        if path is None:
            return 0
        try:
            return sum(item.stat().st_size for item in path.glob("**/*") if item.is_file())
        except OSError:
            return 0

    def _clear_asr_cache_only(self) -> None:
        clear_asr_transcript_cache()
        self._refresh_task_center()

    def _clear_text_cache_only(self) -> None:
        clear_workflow_text_cache()
        self._refresh_task_center()

    def _clear_tts_cache_only(self) -> None:
        clear_tts_cache()
        self._refresh_task_center()

    def _show_workflow_health(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr("workflow_health_title"))
        layout = QVBoxLayout(dialog)
        intro = QLabel(self._tr("workflow_health_summary"), dialog)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        table = QTableWidget(0, 4, dialog)
        table.setHorizontalHeaderLabels(
            [
                self._tr("workflow_health_workflow"),
                self._tr("workflow_health_preset"),
                self._tr("workflow_health_baseline"),
                self._tr("workflow_health_status"),
            ]
        )
        rows = self._workflow_health_rows()
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(760, 360)
        dialog.exec()

    def _workflow_health_action_label(self) -> str:
        title = self._tr("workflow_health_title")
        return f"{title} !" if self._workflow_health_has_slow_stage() else title

    def _workflow_health_has_slow_stage(self) -> bool:
        slow_prefix = self._tr("workflow_health_slow").split("{stages}", 1)[0]
        return any(str(row[3]).startswith(slow_prefix) for row in self._workflow_health_rows())

    def _workflow_health_rows(self) -> list[tuple[str, str, str, str]]:
        baseline_path = PROJECT_ROOT / "docs" / "workflow_benchmark_baselines.json"
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return [("baseline", "", str(baseline_path), self._tr("workflow_health_missing_baseline"))]
        workflows = data.get("workflows") if isinstance(data, dict) else {}
        if not isinstance(workflows, dict) or not workflows:
            return [("baseline", "", str(baseline_path), self._tr("workflow_health_missing_baseline"))]
        current = self._load_current_workflow_benchmark()
        rows: list[tuple[str, str, str, str]] = []
        for name, entry in sorted(workflows.items()):
            result = entry.get("result") if isinstance(entry, dict) else {}
            timings = result.get("timings") if isinstance(result, dict) else {}
            baseline_seconds = sum(float(value) for value in timings.values() if isinstance(value, int | float))
            status = self._workflow_health_status(current, result if isinstance(result, dict) else {})
            rows.append((str(name), str(result.get("preset", "")), f"{baseline_seconds:.1f}s", status))
        return rows

    def _load_current_workflow_benchmark(self) -> dict[str, object]:
        for path in (
            RUNTIME_DIR / "workflow_benchmark.json",
            RUNTIME_DIR / "workflow-benchmark-current.json",
            PROJECT_ROOT / "data" / "tmp" / "workflow-benchmark-current.json",
        ):
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
        return {}

    def _workflow_health_status(self, current: dict[str, object], baseline: dict[str, object]) -> str:
        if not current:
            return self._tr("workflow_health_needs_run")
        current_timings = current.get("timings") if isinstance(current, dict) else {}
        baseline_timings = baseline.get("timings") if isinstance(baseline, dict) else {}
        if not isinstance(current_timings, dict) or not isinstance(baseline_timings, dict):
            return self._tr("workflow_health_needs_run")
        slow = []
        for key, baseline_value in baseline_timings.items():
            if key not in current_timings:
                continue
            try:
                current_seconds = float(current_timings[key])
                baseline_seconds = float(baseline_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if baseline_seconds > 0 and current_seconds > baseline_seconds * 1.35:
                slow.append(key.replace("_seconds", ""))
        if slow:
            return self._tr("workflow_health_slow").format(stages=", ".join(slow))
        return self._tr("workflow_health_ok")

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
