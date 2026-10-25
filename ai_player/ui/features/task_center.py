from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_player.adapters.ai.asr import asr_transcript_cache_stats, clear_asr_transcript_cache
from ai_player.adapters.sources.adult_extractors import (
    AdultHostSupport,
    supported_adult_host_summary,
    supported_adult_hosts,
)
from ai_player.adapters.sources.video_source import CACHE_MAX_AGE_SECONDS, default_video_cache_root
from ai_player.adapters.storage.workflow_cache import clear_workflow_text_cache, workflow_text_cache_stats
from ai_player.adapters.tts.tts_base import clear_tts_cache, tts_cache_stats
from ai_player.configuration import PROJECT_ROOT, RUNTIME_DIR
from ai_player.ui.features.base import Feature
from ai_player.ui.task_center import BackgroundTask, collect_background_tasks, stop_background_tasks


class PlayerTaskCenterFeature(Feature):
    def _task_center_tab(self) -> QWidget:
        tab = QWidget()
        self.context.task_center._task_center_tab_widget = tab
        self.context.task_center._task_center_log: list[str] = self.context.get("_task_center_log", [])
        self.context.task_center._task_center_retry_action: Callable[[], None] | None = None
        self.context.task_center._task_center_retry_label = ""

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(8)

        summary = QLabel(self.context.settings._tr("task_center_summary"))
        summary.setProperty("i18n_key", "task_center_summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.context.task_center._task_center_stop_button = self.context.ui._make_button(
            "task_center_stop_all",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self.context.task_center._task_center_stop_button.clicked.connect(
            self.context.task_center._stop_task_center_tasks
        )
        self.context.task_center._task_center_retry_button = self.context.ui._make_button(
            "task_center_retry",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.task_center._task_center_retry_button.clicked.connect(
            self.context.task_center._retry_task_center_action
        )
        self.context.task_center._task_center_refresh_button = self.context.ui._make_button(
            "task_center_refresh",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.task_center._task_center_refresh_button.clicked.connect(
            self.context.task_center._refresh_task_center
        )
        toolbar_layout.addWidget(self.context.task_center._task_center_stop_button)
        toolbar_layout.addWidget(self.context.task_center._task_center_retry_button)
        toolbar_layout.addWidget(self.context.task_center._task_center_refresh_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        self.context.task_center._task_center_table = QTableWidget(0, 3)
        self.context.task_center._task_center_table.setObjectName("taskCenterTable")
        self.context.task_center._task_center_table.setHorizontalHeaderLabels(
            [
                self.context.settings._tr("task_center_name"),
                self.context.settings._tr("task_center_status"),
                self.context.settings._tr("task_center_detail"),
            ]
        )
        self.context.task_center._task_center_table.verticalHeader().setVisible(False)
        self.context.task_center._task_center_table.setWordWrap(True)
        self.context.task_center._task_center_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.context.task_center._task_center_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.context.task_center._task_center_table.setColumnWidth(0, 150)
        self.context.task_center._task_center_table.setColumnWidth(1, 90)
        self.context.task_center._task_center_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.context.task_center._task_center_table, 2)

        layout.addWidget(self.context.ui._section_title("task_center_log_title"))
        self.context.task_center._task_center_log_view = QPlainTextEdit()
        self.context.task_center._task_center_log_view.setReadOnly(True)
        self.context.task_center._task_center_log_view.setMaximumBlockCount(160)
        self.context.task_center._task_center_log_view.setMinimumHeight(120)
        self.context.task_center._task_center_log_view.setPlaceholderText(
            self.context.settings._tr("task_center_log_empty")
        )
        self.context.task_center._task_center_log_view.setProperty("i18n_key", "task_center_log_empty")
        layout.addWidget(self.context.task_center._task_center_log_view, 1)

        self.context.task_center._refresh_task_center()
        return tab

    def _task_center_tab_changed(self, index: int) -> None:
        if self.context.has("_task_center_tab_widget") and self.context.runtime._settings_tab_contains(
            self.context.layout._settings_tabs.widget(index), self.context.task_center._task_center_tab_widget
        ):
            self.context.task_center._refresh_task_center()

    def _refresh_task_center(self) -> None:
        if not self.context.has("_task_center_table"):
            return
        tasks = collect_background_tasks(self.context)
        info_tasks = self.context.task_center._task_center_info_tasks()
        rows = self.context.task_center._task_center_rows(tasks, info_tasks)
        self.context.task_center._task_center_table.setRowCount(len(rows) or 1)
        if not rows:
            self.context.task_center._set_task_center_row(
                0, self.context.settings._tr("task_center_idle"), "", self.context.settings._tr("runtime_tasks_idle")
            )
        else:
            for row, task in enumerate(rows):
                self.context.task_center._set_task_center_row(row, task.name, task.status, task.detail)
        self.context.task_center._task_center_table.resizeRowsToContents()
        self.context.task_center._task_center_stop_button.setEnabled(bool(tasks))
        self.context.task_center._task_center_retry_button.setEnabled(
            self.context.task_center._task_center_retry_action is not None
        )
        retry_label = self.context.task_center._task_center_retry_label or self.context.settings._tr(
            "task_center_retry_unavailable"
        )
        self.context.task_center._task_center_retry_button.setToolTip(retry_label)
        self.context.task_center._refresh_task_center_log()
        self.context.task_center._refresh_global_task_status(tasks)
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()

    def _task_center_rows(
        self,
        tasks: tuple[BackgroundTask, ...],
        info_tasks: tuple[BackgroundTask, ...],
    ) -> tuple[BackgroundTask, ...]:
        rows: list[BackgroundTask] = []
        if tasks:
            rows.append(BackgroundTask(self.context.settings._tr("task_center_group_running"), "", ""))
            for task in tasks:
                rows.extend(self.context.task_center._task_timeline_rows(task))
        if info_tasks:
            rows.append(BackgroundTask(self.context.settings._tr("task_center_group_cache"), "", ""))
            rows.extend(info_tasks)
            cache_hit = self.context.task_center._cache_hit_task()
            if cache_hit is not None:
                rows.append(cache_hit)
        last_error = str(self.context.get("_task_center_last_error", "") or "").strip()
        if last_error:
            rows.append(BackgroundTask(self.context.settings._tr("task_center_group_errors"), "", ""))
            rows.append(
                BackgroundTask(
                    self.context.settings._tr("task_center_last_error"),
                    self.context.settings._tr("task_status_error"),
                    last_error,
                )
            )
        return tuple(rows)

    def _task_timeline_rows(self, task: BackgroundTask) -> tuple[BackgroundTask, ...]:
        return (
            BackgroundTask(
                task.name,
                self.context.settings._tr("task_center_timeline_prepare"),
                self.context.settings._tr("task_center_timeline_ready"),
            ),
            BackgroundTask(task.name, self.context.settings._tr("task_center_timeline_process"), task.detail),
            BackgroundTask(
                task.name,
                self.context.settings._tr("task_center_timeline_done"),
                self.context.settings._tr("task_center_timeline_pending"),
            ),
        )

    def _cache_hit_task(self) -> BackgroundTask | None:
        asr = asr_transcript_cache_stats()
        text = workflow_text_cache_stats()
        tts = tts_cache_stats()
        hits = int(asr.get("hits", 0)) + int(text.get("hits", 0)) + int(tts.get("hits", 0))
        if hits <= 0:
            return None
        return BackgroundTask(
            self.context.settings._tr("task_center_cache_hit"),
            self.context.settings._tr("task_center_timeline_done"),
            self.context.settings._tr("task_center_cache_hit_detail").format(count=hits),
        )

    def _task_center_info_tasks(self) -> tuple[BackgroundTask, ...]:
        detail = self.context.task_center._workflow_cache_summary()
        if not detail:
            return ()
        return (
            BackgroundTask(
                self.context.settings._tr("task_center_cache_name"),
                self.context.settings._tr("task_center_cache_status"),
                detail,
            ),
        )

    def _workflow_cache_summary(self) -> str:
        asr = asr_transcript_cache_stats()
        text = workflow_text_cache_stats()
        tts = tts_cache_stats()
        total_activity = sum(
            int(stats.get(key, 0)) for stats in (asr, text, tts) for key in ("hits", "misses", "writes", "entries")
        ) + int(self.context.get("_url_cache_completed_count", 0) or 0)
        if total_activity <= 0:
            return ""
        return self.context.settings._tr("task_center_cache_detail").format(
            asr_hits=asr.get("hits", 0),
            asr_writes=asr.get("writes", 0),
            text_hits=text.get("hits", 0),
            text_writes=text.get("writes", 0),
            tts_hits=tts.get("hits", 0),
            tts_writes=tts.get("writes", 0),
            url_cached=int(self.context.get("_url_cache_completed_count", 0) or 0),
            entries=asr.get("entries", 0) + text.get("entries", 0) + tts.get("entries", 0),
        )

    def _refresh_global_task_status(self, tasks=None) -> None:
        button = self.context.get("_task_status_button", None)
        if button is None:
            return
        if tasks is None:
            tasks = collect_background_tasks(self.context)
        active = [task for task in tasks if task.status == "RUNNING"]
        if not active:
            has_error = self.context.get("_task_center_retry_action", None) is not None
            button.setText(self.context.settings._tr("task_status_error" if has_error else "task_status_idle"))
            button.setToolTip(self.context.settings._tr("task_status_tooltip"))
            button.setProperty("activeTasks", "error" if has_error else "false")
            self.context.task_center._refresh_task_drawer_summary(
                self.context.settings._tr("task_drawer_idle"), active=False
            )
        else:
            count = len(active)
            first = active[0]
            detail = " ".join(str(first.detail or "").split())
            if len(detail) > 72:
                detail = f"{detail[:69]}..."
            button.setText(self.context.settings._tr("task_status_active"))
            button.setToolTip(f"{first.name}: {detail}" if detail else first.name)
            button.setProperty("activeTasks", "true")
            summary = self.context.settings._tr("task_drawer_running").format(
                count=count,
                task=first.name,
                detail=detail or first.status,
            )
            self.context.task_center._refresh_task_drawer_summary(summary, active=True)
        button.style().unpolish(button)
        button.style().polish(button)

    def _refresh_task_drawer_summary(self, text: str, *, active: bool) -> None:
        drawer = self.context.get("_task_drawer", None)
        has_error = self.context.get("_task_center_retry_action", None) is not None
        if drawer is not None:
            if active:
                state = "true"
            elif has_error:
                state = "error"
            else:
                state = "false"
            drawer.setProperty("activeTasks", state)
            style = drawer.style()
            style.unpolish(drawer)
            style.polish(drawer)
            if active:
                self.context.layout._task_drawer_user_open = False
                drawer.setVisible(not self.context.task_center._task_drawer_hidden_for_video_playback())
            elif has_error:
                drawer.setVisible(True)
            elif not self.context.get("_task_drawer_user_open", False):
                drawer.hide()
        state_label = self.context.get("_task_drawer_state", None)
        if state_label is not None:
            if active:
                label_key = "task_drawer_state_running"
                status = "active"
            elif has_error:
                label_key = "task_drawer_state_error"
                status = "error"
            else:
                label_key = "task_drawer_state_idle"
                status = "idle"
            state_label.setText(self.context.settings._tr(label_key))
            state_label.setProperty("i18n_key", label_key)
            state_label.setProperty("status", status)
            state_label.style().unpolish(state_label)
            state_label.style().polish(state_label)
        summary = self.context.get("_task_drawer_summary", None)
        if summary is not None:
            if has_error and not active:
                last_error = str(self.context.get("_task_center_last_error", "") or "").strip()
                summary.setText(last_error or text)
            else:
                summary.setText(text)
            summary.setProperty("i18n_key", "task_drawer_idle" if not active else "")
        stop_button = self.context.get("_task_drawer_stop_button", None)
        if stop_button is not None:
            stop_button.setEnabled(active)
        retry_button = self.context.get("_task_drawer_retry_button", None)
        if retry_button is not None:
            retry_button.setEnabled(self.context.get("_task_center_retry_action", None) is not None)

    def _task_drawer_hidden_for_video_playback(self) -> bool:
        if self.context.get("_document_mode", False):
            return False
        player = self.context.get("_player", None)
        is_playing = getattr(player, "is_playing", None)
        return bool(callable(is_playing) and is_playing())

    def _set_task_center_row(self, row: int, name: str, status: str, detail: str) -> None:
        values = (name, status, detail)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value or ""))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.context.task_center._task_center_table.setItem(row, column, item)

    def _record_task_center_event(self, name: str, detail: object) -> None:
        text = " ".join(str(detail or "").split())
        if not text:
            return
        if not self.context.has("_task_center_log"):
            self.context.task_center._task_center_log = []
        entry = f"{name}: {text[:500]}"
        if not self.context.task_center._task_center_log or self.context.task_center._task_center_log[-1] != entry:
            self.context.task_center._task_center_log.append(entry)
            self.context.task_center._task_center_log = self.context.task_center._task_center_log[-80:]
        self.context.task_center._refresh_task_center()

    def _refresh_task_center_log(self) -> None:
        if not self.context.has("_task_center_log_view"):
            return
        self.context.task_center._task_center_log_view.setPlainText(
            "\n".join(self.context.get("_task_center_log", [])[-80:])
        )

    def _set_task_center_retry(self, label: str, action: Callable[[], None] | None) -> None:
        self.context.task_center._task_center_retry_label = str(label or "")
        self.context.task_center._task_center_retry_action = action
        if action is not None and self.context.task_center._task_center_retry_label:
            self.context.task_center._task_center_last_error = self.context.task_center._task_center_retry_label
        self.context.task_center._refresh_task_center()

    def _clear_workflow_caches(self) -> None:
        clear_asr_transcript_cache()
        clear_workflow_text_cache()
        clear_tts_cache()
        self.context.sources._url_cache_completed_count = 0
        self.context.task_center._task_center_last_error = ""
        self.context.task_center._record_task_center_event(
            self.context.settings._tr("task_center_cache_name"), self.context.settings._tr("task_center_cache_cleared")
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("task_center_cache_cleared"))
        self.context.task_center._refresh_task_center()

    def _show_cache_inspector(self) -> None:
        dialog = QDialog(self.context.window)
        dialog.setWindowTitle(self.context.settings._tr("cache_inspector_title"))
        layout = QVBoxLayout(dialog)
        rows = self.context.task_center._cache_inspector_rows()
        table = QTableWidget(len(rows), 4, dialog)
        table.setHorizontalHeaderLabels(
            [
                self.context.settings._tr("cache_inspector_cache"),
                self.context.settings._tr("cache_inspector_entries"),
                self.context.settings._tr("cache_inspector_size"),
                self.context.settings._tr("cache_inspector_activity"),
            ]
        )
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
            ("cache_inspector_clear_asr", self.context.task_center._clear_asr_cache_only),
            ("cache_inspector_clear_text", self.context.task_center._clear_text_cache_only),
            ("cache_inspector_clear_tts", self.context.task_center._clear_tts_cache_only),
            ("cache_inspector_clear_url_site", self.context.task_center._clear_video_url_cache_site),
            ("cache_inspector_clear_url_old", self.context.task_center._clear_old_video_url_cache),
            ("cache_inspector_clear_url", self.context.task_center._clear_video_url_cache),
            ("cache_inspector_clear_all", self.context.task_center._clear_workflow_caches),
        ):
            button = QPushButton(self.context.settings._tr(label_key), dialog)
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
            self.context.task_center._cache_inspector_row("ASR", asr, RUNTIME_DIR / "asr-cache"),
            self.context.task_center._cache_inspector_row("Text", text, None),
            self.context.task_center._cache_inspector_row("TTS", tts, RUNTIME_DIR / "tts-cache"),
            self.context.task_center._video_cache_inspector_row(),
        ]

    def _cache_inspector_row(self, name: str, stats: dict[str, int], path) -> tuple[str, int, str, str]:
        return (
            name,
            int(stats.get("entries", 0)),
            self.context.runtime._format_bytes(self.context.task_center._cache_dir_size(path))
            if path is not None
            else "-",
            self.context.settings._tr("cache_inspector_activity").format(
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
        self.context.task_center._refresh_task_center()

    def _clear_text_cache_only(self) -> None:
        clear_workflow_text_cache()
        self.context.task_center._refresh_task_center()

    def _clear_tts_cache_only(self) -> None:
        clear_tts_cache()
        self.context.task_center._refresh_task_center()

    def _video_cache_inspector_row(self) -> tuple[str, int, str, str]:
        root = self.context.task_center._video_url_cache_root()
        files = self.context.task_center._cache_files(root)
        site_count = len({path.relative_to(root).parts[0] for path in files if len(path.relative_to(root).parts) > 1})
        return (
            "URL video",
            len(files),
            self.context.runtime._format_bytes(sum(path.stat().st_size for path in files)),
            f"{site_count} sites / {root}",
        )

    def _video_url_cache_root(self):
        configured = str(getattr(self.context.config, "video_cache_dir", "") or "").strip()
        if configured:
            return Path(configured) / "ai-player-sources"
        return default_video_cache_root()

    def _clear_old_video_url_cache(self) -> None:
        root = self.context.task_center._video_url_cache_root()
        cutoff = time.time() - CACHE_MAX_AGE_SECONDS
        for path in self.context.task_center._cache_files(root):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass
        self.context.task_center._remove_empty_cache_dirs(root)
        self.context.task_center._refresh_task_center()
        self.context.window.statusBar().showMessage(self.context.settings._tr("cache_inspector_url_old_cleared"))

    def _clear_video_url_cache_site(self) -> None:
        root = self.context.task_center._video_url_cache_root()
        sites = self.context.task_center._video_cache_site_names(root)
        if not sites:
            self.context.window.statusBar().showMessage(self.context.settings._tr("cache_inspector_url_empty"))
            return
        site, accepted = QInputDialog.getItem(
            self.context.window,
            self.context.settings._tr("cache_inspector_clear_url_site"),
            self.context.settings._tr("cache_inspector_url_site"),
            sites,
            0,
            False,
        )
        if not accepted or not site:
            return
        try:
            shutil.rmtree(root / str(site))
        except OSError:
            pass
        self.context.task_center._refresh_task_center()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("cache_inspector_url_site_cleared").format(site=site)
        )

    def _clear_video_url_cache(self) -> None:
        root = self.context.task_center._video_url_cache_root()
        try:
            if root.exists():
                shutil.rmtree(root)
        except OSError:
            pass
        self.context.sources._url_cache_completed_count = 0
        self.context.task_center._refresh_task_center()
        self.context.window.statusBar().showMessage(self.context.settings._tr("cache_inspector_url_cleared"))

    @staticmethod
    def _cache_files(root) -> list[Path]:
        try:
            return [item for item in Path(root).glob("**/*") if item.is_file()]
        except OSError:
            return []

    @staticmethod
    def _video_cache_site_names(root) -> list[str]:
        try:
            return sorted(item.name for item in Path(root).iterdir() if item.is_dir())
        except OSError:
            return []

    @staticmethod
    def _remove_empty_cache_dirs(root) -> None:
        try:
            dirs = [item for item in Path(root).glob("**/*") if item.is_dir()]
        except OSError:
            return
        for path in sorted(dirs, key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass

    def _show_workflow_health(self) -> None:
        dialog = QDialog(self.context.window)
        dialog.setWindowTitle(self.context.settings._tr("workflow_health_title"))
        layout = QVBoxLayout(dialog)
        intro = QLabel(self.context.settings._tr("workflow_health_summary"), dialog)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        table = QTableWidget(0, 4, dialog)
        table.setHorizontalHeaderLabels(
            [
                self.context.settings._tr("workflow_health_workflow"),
                self.context.settings._tr("workflow_health_preset"),
                self.context.settings._tr("workflow_health_baseline"),
                self.context.settings._tr("workflow_health_status"),
            ]
        )
        rows = self.context.task_center._workflow_health_rows()
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

    def _show_adult_extractor_health(self) -> None:
        url, accepted = QInputDialog.getText(
            self.context.window,
            self.context.settings._tr("adult_health_title"),
            self.context.settings._tr("adult_health_url"),
        )
        if not accepted or not str(url or "").strip():
            return
        command = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "probe_adult_site.py"),
            str(url).strip(),
            "--output",
            str(PROJECT_ROOT / "data" / "tmp" / "adult-site-probe"),
        ]
        dialog = QDialog(self.context.window)
        dialog.setWindowTitle(self.context.settings._tr("adult_health_title"))
        layout = QVBoxLayout(dialog)
        output = QPlainTextEdit(dialog)
        output.setReadOnly(True)
        output.setPlainText(self.context.settings._tr("adult_health_running"))
        layout.addWidget(output, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.resize(760, 480)
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
            output.setPlainText(self.context.task_center._adult_health_report_text(result))
        except Exception as exc:
            output.setPlainText(f"{self.context.settings._tr('adult_health_failed')}: {exc}")
        dialog.exec()

    def _adult_health_report_text(self, result: subprocess.CompletedProcess) -> str:
        text = str(result.stdout or "").strip()
        if text:
            try:
                report = json.loads(text)
            except json.JSONDecodeError:
                report = None
            if isinstance(report, dict):
                media = report.get("media_candidates") if isinstance(report.get("media_candidates"), list) else []
                extractors = (
                    report.get("extractor_candidates") if isinstance(report.get("extractor_candidates"), list) else []
                )
                health_key = "adult_health_ok" if result.returncode == 0 else "adult_health_attention"
                lines = [
                    f"{self.context.settings._tr('adult_health_status')}: {self.context.settings._tr(health_key)}",
                    f"Host: {report.get('host') or '-'}",
                    f"Extractor: {', '.join(str(item) for item in extractors) or '-'}",
                    f"JSON payloads: {report.get('json_payload_count') or 0}",
                    f"Iframe: {report.get('iframe_candidate') or '-'}",
                    f"Media candidates: {len(media)}",
                ]
                lines.extend(f"- {item}" for item in media[:12])
                lines.append(f"Fixture: {report.get('html_fixture') or '-'}")
                lines.append(f"Registry draft: {report.get('registry_draft') or '-'}")
                return "\n".join(lines)
        stderr = str(result.stderr or "").strip()
        return "\n\n".join(part for part in (text, stderr, f"exit={result.returncode}") if part)

    def _show_adult_supported_hosts(self) -> None:
        rows = supported_adult_hosts()
        summary = supported_adult_host_summary()
        dialog = QDialog(self.context.window)
        dialog.setWindowTitle(self.context.settings._tr("adult_hosts_title"))
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            self.context.settings._tr("adult_hosts_summary").format(
                sites=summary["sites"],
                hosts=summary["hosts"],
                delegate=summary["delegate"],
                generic=summary["generic"],
                site_specific=summary["site_specific"],
            ),
            dialog,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        table = QTableWidget(0, 6, dialog)
        table.setHorizontalHeaderLabels(
            [
                self.context.settings._tr("adult_hosts_open"),
                self.context.settings._tr("adult_hosts_site"),
                self.context.settings._tr("adult_hosts_domains"),
                self.context.settings._tr("adult_hosts_intro"),
                self.context.settings._tr("adult_hosts_mode"),
                self.context.settings._tr("adult_hosts_notes"),
            ]
        )
        table.setRowCount(len(rows))
        for row, support in enumerate(rows):
            table.setCellWidget(row, 0, self.context.task_center._adult_host_open_button(support))
            values = self.context.task_center._adult_host_row_values(support)
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(1080, 560)
        dialog.exec()

    def _adult_host_row_values(self, support: AdultHostSupport) -> tuple[str, str, str, str, str]:
        notes = []
        if support.iframe_depth is not None:
            notes.append(f"iframe_depth={support.iframe_depth}")
        if support.accept_language:
            notes.append(f"lang={support.accept_language}")
        return (
            support.site_key,
            ", ".join(support.domains),
            support.description,
            self.context.task_center._adult_host_mode_label(support.mode),
            "; ".join(notes),
        )

    def _adult_host_open_button(self, support: AdultHostSupport) -> QPushButton:
        button = QPushButton(self.context.settings._tr("adult_hosts_open"))
        button.setEnabled(bool(support.open_url))
        if support.open_url:
            button.setToolTip(support.open_url)
            button.clicked.connect(
                lambda _checked=False, url=support.open_url: self.context.task_center._open_adult_host_url(url)
            )
        return button

    def _open_adult_host_url(self, url: str) -> None:
        opener = self.context.get("_open_video_url_in_browser", None)
        if callable(opener) and opener(url):
            return
        placeholder = self.context.get("_video_placeholder", None)
        media_stack = self.context.get("_media_stack", None)
        set_url = getattr(placeholder, "setUrl", None)
        if callable(set_url):
            set_url(QUrl(url))
            if media_stack is not None:
                media_stack.setCurrentWidget(placeholder)
            sync = self.context.get("_sync_media_browser_state", None)
            if callable(sync):
                sync()

    def _adult_host_mode_label(self, mode: str) -> str:
        labels = {
            "yt-dlp native": self.context.settings._tr("adult_hosts_mode_ytdlp"),
            "generic": self.context.settings._tr("adult_hosts_mode_generic"),
            "site-specific": self.context.settings._tr("adult_hosts_mode_specific"),
        }
        return labels.get(mode, mode)

    def _workflow_health_action_label(self) -> str:
        title = self.context.settings._tr("workflow_health_title")
        return f"{title} !" if self.context.task_center._workflow_health_has_slow_stage() else title

    def _workflow_health_has_slow_stage(self) -> bool:
        slow_prefix = self.context.settings._tr("workflow_health_slow").split("{stages}", 1)[0]
        return any(str(row[3]).startswith(slow_prefix) for row in self.context.task_center._workflow_health_rows())

    def _workflow_health_rows(self) -> list[tuple[str, str, str, str]]:
        baseline_path = PROJECT_ROOT / "docs" / "workflow_benchmark_baselines.json"
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return [("baseline", "", str(baseline_path), self.context.settings._tr("workflow_health_missing_baseline"))]
        workflows = data.get("workflows") if isinstance(data, dict) else {}
        if not isinstance(workflows, dict) or not workflows:
            return [("baseline", "", str(baseline_path), self.context.settings._tr("workflow_health_missing_baseline"))]
        current = self.context.task_center._load_current_workflow_benchmark()
        rows: list[tuple[str, str, str, str]] = []
        for name, entry in sorted(workflows.items()):
            result = entry.get("result") if isinstance(entry, dict) else {}
            timings = result.get("timings") if isinstance(result, dict) else {}
            baseline_seconds = sum(float(value) for value in timings.values() if isinstance(value, int | float))
            status = self.context.task_center._workflow_health_status(
                current, result if isinstance(result, dict) else {}
            )
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
            return self.context.settings._tr("workflow_health_needs_run")
        current_timings = current.get("timings") if isinstance(current, dict) else {}
        baseline_timings = baseline.get("timings") if isinstance(baseline, dict) else {}
        if not isinstance(current_timings, dict) or not isinstance(baseline_timings, dict):
            return self.context.settings._tr("workflow_health_needs_run")
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
            return self.context.settings._tr("workflow_health_slow").format(stages=", ".join(slow))
        return self.context.settings._tr("workflow_health_ok")

    def _retry_task_center_action(self) -> None:
        action = self.context.get("_task_center_retry_action", None)
        if action is None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("task_center_retry_unavailable"))
            return
        action()
        self.context.window.statusBar().showMessage(self.context.settings._tr("task_center_retry_started"))
        self.context.task_center._refresh_task_center()

    def _stop_task_center_tasks(self) -> None:
        if self.context.get("_closing", False):
            return
        if not self.context.has("_task_stop_timer"):
            self.context.task_center._task_stop_timer = QTimer(self.context.window)
            self.context.task_center._task_stop_timer.setSingleShot(True)
            self.context.task_center._task_stop_timer.timeout.connect(self.context.task_center._poll_task_center_stop)
        if not self.context.task_center._task_stop_timer.isActive():
            self.context.task_center._task_stop_count = len(collect_background_tasks(self.context))
        self.context.task_center._poll_task_center_stop()

    def _poll_task_center_stop(self) -> None:
        if self.context.get("_closing", False):
            return
        summary = stop_background_tasks(self.context, wait_ms=0)
        self.context.task_center._refresh_task_center()
        if summary.failed:
            message = self.context.settings._tr("runtime_tasks_stopping").format(tasks=", ".join(summary.failed))
            self.context.task_center._task_stop_timer.start(100)
        else:
            self.context.task_center._task_stop_timer.stop()
            message = self.context.settings._tr("runtime_tasks_stopped").format(
                count=self.context.task_center._task_stop_count
            )
        self.context.window.statusBar().showMessage(message)
