from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from ai_player.ui.features.base import Feature
from ai_player.ui.features.media_browser import DEFAULT_MEDIA_HOME_URL
from ai_player.ui.player_window_utils import (
    html_with_breaks as _html_with_breaks,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)


class PlayerTranscriptFeature(Feature):
    def _append_segment(self, original: str, translated: str) -> None:
        self.context.transcript._append_dubbing_segment(original, translated)
        self.context.dubbing._set_live_subtitle(original, translated)

    def _append_dubbing_segment(self, original: str, translated: str) -> None:
        self.context.transcript._transcript_segments.append(
            self.context.transcript._make_transcript_segment(original, translated)
        )
        self.context.transcript._render_transcript()

    def _selected_transcript_view(self) -> str:
        if not self.context.has("_transcript_view_combo"):
            return "all"
        return self.context.transcript._normalize_transcript_view(
            self.context.layout._transcript_view_combo.currentData()
        )

    def _selected_transcript_type(self) -> str:
        if not self.context.has("_transcript_type_combo"):
            return "all"
        return self.context.transcript._normalize_transcript_type(
            self.context.layout._transcript_type_combo.currentData()
        )

    def _render_transcript(self, *_args) -> None:
        if self.context.has("_transcript"):
            self.context.layout._transcript.setHtml(
                self.context.transcript._transcript_html(
                    self.context.transcript._selected_transcript_view(),
                    self.context.transcript._selected_transcript_type(),
                )
            )
        self.context.transcript._refresh_transcript_segment_table()
        self.context.transcript._refresh_next_action_panel()

    def _clear_transcript(self) -> None:
        self.context.transcript._transcript_segments.clear()
        if self.context.has("_transcript"):
            self.context.layout._transcript.clear()
        self.context.transcript._refresh_transcript_segment_table()
        self.context.transcript._refresh_next_action_panel()

    def _set_transcript_text(self, text: str, *, source_only: bool = True) -> None:
        clean = _repair_mojibake(str(text or "").strip())
        if clean:
            target = "" if source_only else clean
            self.context.transcript._transcript_segments = [
                self.context.transcript._make_transcript_segment(clean, target)
            ]
        else:
            self.context.transcript._transcript_segments = []
        self.context.transcript._render_transcript()

    def _refresh_transcript_segment_table(self) -> None:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return
        self.context.transcript._refresh_transcript_status_strip()
        selected_row = table.currentRow()
        has_segments = bool(self.context.transcript._transcript_segments)
        table.setVisible(has_segments)
        table.setRowCount(len(self.context.transcript._transcript_segments))
        if not self.context.transcript._transcript_segments:
            self.context.transcript._sync_transcript_segment_editor(-1)
            self.context.transcript._sync_transcript_segment_banner()
            self.context.transcript._refresh_transcript_empty_state()
            return
        for row, segment in enumerate(self.context.transcript._transcript_segments):
            normalized = self.context.transcript._normalize_transcript_segment(segment)
            source = normalized.get("source", {}).get("cleaned", "") or normalized.get("source", {}).get("raw", "")
            target = normalized.get("target", {}).get("cleaned", "") or normalized.get("target", {}).get("raw", "")
            status = self.context.transcript._transcript_segment_status(normalized, target)
            self.context.transcript._set_transcript_segment_row(row, str(row + 1), source, target, status)
            self.context.transcript._style_transcript_segment_row(row, normalized, bool(target))
        self.context.transcript._apply_transcript_filter()
        if selected_row < 0 or selected_row >= len(self.context.transcript._transcript_segments):
            selected_row = 0
        if table.isRowHidden(selected_row):
            selected_row = self.context.transcript._first_visible_transcript_row()
        if selected_row >= 0:
            table.selectRow(selected_row)
        table.resizeRowsToContents()
        self.context.transcript._sync_transcript_segment_editor(selected_row)
        self.context.transcript._sync_transcript_segment_banner()
        self.context.transcript._refresh_transcript_empty_state()

    def _set_transcript_segment_row(self, row: int, index: str, source: str, target: str, status: str) -> None:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return
        content_lines = []
        if source:
            content_lines.append(f"{self.context.settings._tr('transcript_label_source')}: {source}")
        if target:
            content_lines.append(f"{self.context.settings._tr('transcript_label_target')}: {target}")
        content = "\n".join(content_lines) or self.context.settings._tr("transcript_segment_empty")
        for column, value in enumerate((index, content, status)):
            item = QTableWidgetItem(_repair_mojibake(str(value or "")))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)

    def _style_transcript_segment_row(self, row: int, segment: dict, has_target: bool) -> None:
        from ai_player.resources.themes.python_theme import values

        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return
        theme = values()
        metadata = segment.get("metadata", {}) if isinstance(segment, dict) else {}
        if isinstance(metadata, dict) and metadata.get("retry_requested"):
            color = QColor(theme["warning-soft"])
        elif isinstance(metadata, dict) and metadata.get("reviewed"):
            color = QColor(theme["success-soft"])
        elif not has_target:
            color = QColor(theme["surface"])
        else:
            color = QColor(theme["panel"])
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is not None:
                item.setBackground(QBrush(color))

    def _refresh_transcript_status_strip(self) -> None:
        labels = self.context.get("_transcript_status_labels", None)
        if not labels:
            return
        segments = [
            self.context.transcript._normalize_transcript_segment(segment)
            for segment in self.context.transcript._transcript_segments
        ]
        total_count = len(segments)
        translated_count = sum(
            1
            for segment in segments
            if (segment.get("target", {}).get("cleaned", "") or segment.get("target", {}).get("raw", "")).strip()
        )
        retry_count = sum(1 for segment in segments if segment.get("metadata", {}).get("retry_requested"))
        state_key = "transcript_status_state_ready" if total_count else "transcript_status_state_empty"
        values = {
            "transcript_status_total": (
                self.context.settings._tr("transcript_status_total").format(count=total_count),
                "ok",
            ),
            "transcript_status_translated": (
                self.context.settings._tr("transcript_status_translated").format(count=translated_count),
                "ok" if translated_count else "muted",
            ),
            "transcript_status_retry": (
                self.context.settings._tr("transcript_status_retry").format(count=retry_count),
                "warn" if retry_count else "muted",
            ),
            "transcript_status_state_empty": (
                self.context.settings._tr(state_key).format(count=total_count),
                "ok" if total_count else "muted",
            ),
        }
        for key, (text, status_kind) in values.items():
            label = labels.get(key)
            if label is None:
                continue
            label.setText(text)
            label.setProperty("status", status_kind)
            label.style().unpolish(label)
            label.style().polish(label)

    def _transcript_segment_status(self, segment: dict, target: str) -> str:
        metadata = segment.get("metadata", {}) if isinstance(segment, dict) else {}
        if isinstance(metadata, dict) and metadata.get("retry_requested"):
            return self.context.settings._tr("transcript_segment_retry_needed")
        if isinstance(metadata, dict) and metadata.get("reviewed"):
            return self.context.settings._tr("transcript_segment_reviewed")
        return (
            self.context.settings._tr("transcript_segment_ready")
            if target
            else self.context.settings._tr("transcript_segment_source_only")
        )

    def _transcript_segment_selection_changed(self) -> None:
        self.context.transcript._sync_transcript_segment_editor(
            self.context.transcript._selected_transcript_segment_index()
        )

    def _set_transcript_filter(self, mode: str) -> None:
        self.context.transcript._transcript_filter = str(mode or "all")
        for value, button in self.context.get("_transcript_filter_buttons", {}).items():
            button.setChecked(value == self.context.transcript._transcript_filter)
        self.context.transcript._apply_transcript_filter()
        self.context.transcript._sync_transcript_segment_editor(
            self.context.transcript._selected_transcript_segment_index()
        )

    def _apply_transcript_filter(self) -> None:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return
        mode = str(self.context.get("_transcript_filter", "all") or "all")
        for row, segment in enumerate(self.context.get("_transcript_segments", [])):
            normalized = self.context.transcript._normalize_transcript_segment(segment)
            table.setRowHidden(row, not self.context.transcript._transcript_segment_matches_filter(normalized, mode))
        current = table.currentRow()
        if current >= 0 and table.isRowHidden(current):
            first = self.context.transcript._first_visible_transcript_row()
            if first >= 0:
                table.selectRow(first)

    def _transcript_segment_matches_filter(self, segment: dict, mode: str) -> bool:
        if mode == "all":
            return True
        metadata = segment.get("metadata", {}) if isinstance(segment, dict) else {}
        target = segment.get("target", {}) if isinstance(segment, dict) else {}
        has_target = (
            bool(str(target.get("cleaned") or target.get("raw") or "").strip()) if isinstance(target, dict) else False
        )
        if mode == "retry":
            return bool(isinstance(metadata, dict) and metadata.get("retry_requested"))
        if mode == "reviewed":
            return bool(isinstance(metadata, dict) and metadata.get("reviewed"))
        if mode == "untranslated":
            return not has_target
        return True

    def _first_visible_transcript_row(self) -> int:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return -1
        for row in range(table.rowCount()):
            if not table.isRowHidden(row):
                return row
        return -1

    def _visible_transcript_segment_indexes(self) -> list[int]:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return []
        return [
            row
            for row in range(min(table.rowCount(), len(self.context.get("_transcript_segments", []))))
            if not table.isRowHidden(row)
        ]

    def _mark_visible_transcript_segments_reviewed(self) -> None:
        indexes = self.context.transcript._visible_transcript_segment_indexes()
        if not indexes:
            self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_no_selection"))
            return
        for index in indexes:
            segment = self.context.transcript._normalize_transcript_segment(
                self.context.transcript._transcript_segments[index]
            )
            metadata = segment.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["reviewed"] = True
                metadata["retry_requested"] = False
            self.context.transcript._transcript_segments[index] = segment
        self.context.transcript._render_transcript()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("transcript_batch_reviewed").format(count=len(indexes))
        )

    def _retry_visible_transcript_segments(self) -> None:
        indexes = self.context.transcript._visible_transcript_segment_indexes()
        if not indexes:
            self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_no_selection"))
            return
        for index in indexes:
            segment = self.context.transcript._normalize_transcript_segment(
                self.context.transcript._transcript_segments[index]
            )
            metadata = segment.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["reviewed"] = False
                metadata["retry_requested"] = True
            self.context.transcript._transcript_segments[index] = segment
        self.context.transcript._render_transcript()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("transcript_batch_retry_marked").format(count=len(indexes))
        )

    def _sync_transcript_segment_banner(self) -> None:
        banner = self.context.get("_transcript_segment_banner", None)
        if banner is None:
            return
        if not self.context.transcript._transcript_segments:
            banner.setVisible(False)
            return
        retry_count = sum(
            1
            for segment in self.context.transcript._transcript_segments
            if self.context.transcript._normalize_transcript_segment(segment).get("metadata", {}).get("retry_requested")
        )
        if retry_count:
            banner.setText(self.context.settings._tr("transcript_segment_retry_banner").format(count=retry_count))
            banner.setVisible(True)
            return
        banner.setVisible(False)

    def _refresh_next_action_panel(self) -> None:
        panel = self.context.get("_next_action_panel", None)
        if panel is None:
            return
        state = self.context.transcript._next_action_state()
        self.context.transcript._apply_next_action_state(panel, state)
        self.context.transcript._refresh_transcript_empty_state()

    def _refresh_transcript_empty_state(self, state: dict[str, object] | None = None) -> None:
        panel = self.context.get("_transcript_empty_panel", None)
        if panel is None:
            return
        has_segments = bool(self.context.get("_transcript_segments", []))
        panel.setVisible(not has_segments)
        if has_segments:
            return
        self.context.transcript._apply_next_action_state(
            panel, state or self.context.transcript._next_action_state(transcript_empty=True)
        )

    def _next_action_state(self, *, transcript_empty: bool = False) -> dict[str, object]:
        if self.context.transcript._has_active_background_tasks():
            return {
                "title": "next_action_task_title",
                "detail": "next_action_task_detail",
                "actions": ["open_tasks"],
            }
        has_source = self.context.transcript._has_open_source()
        has_transcript = self.context.transcript._has_transcript_content()
        transcript_path_edit = self.context.get("_transcript_path_edit", None)
        has_transcript_file = bool(transcript_path_edit is not None and transcript_path_edit.text().strip())
        if not has_source:
            return {
                "title": "next_action_no_source_title",
                "detail": "next_action_no_source_detail",
                "actions": ["choose_workflow"],
            }
        if self.context.get("_document_editor_active", False):
            return {
                "title": "next_action_document_editor_title",
                "detail": "next_action_document_editor_detail",
                "actions": ["start_dubbing"],
            }
        if has_transcript:
            return {
                "title": "next_action_transcript_ready_title",
                "detail": "next_action_transcript_ready_detail",
                "actions": ["export"],
            }
        if has_transcript_file:
            return {
                "title": "next_action_transcript_file_title",
                "detail": "next_action_transcript_file_detail",
                "actions": ["start_dubbing"],
            }
        if transcript_empty:
            detail = "next_action_transcript_empty_detail"
        else:
            detail = "next_action_source_ready_detail"
        return {
            "title": "next_action_source_ready_title",
            "detail": detail,
            "actions": ["start_dubbing"],
        }

    def _apply_next_action_state(self, panel, state: dict[str, object]) -> None:
        title = getattr(panel, "_next_action_title", None)
        detail = getattr(panel, "_next_action_detail", None)
        buttons = list(getattr(panel, "_next_action_buttons", []) or [])
        if title is not None:
            title.setText(self.context.settings._tr(str(state.get("title") or "next_action_title")))
        if detail is not None:
            detail.setText(self.context.settings._tr(str(state.get("detail") or "next_action_no_source_detail")))
        action_keys = [str(action or "") for action in list(state.get("actions") or [])[: len(buttons)]]
        panel._next_action_keys = action_keys
        for index, button in enumerate(buttons):
            action_key = action_keys[index] if index < len(action_keys) else ""
            if not action_key:
                button.hide()
                continue
            button.setText(self.context.settings._tr(f"next_action_button_{action_key}"))
            button.setToolTip(self.context.settings._tr(f"next_action_button_{action_key}"))
            button.show()
        self.context.transcript._apply_next_action_checklist(panel)

    def _apply_next_action_checklist(self, panel) -> None:
        checklist = getattr(panel, "_next_action_checklist", None)
        if not checklist:
            return
        statuses = self.context.transcript._next_action_checklist_statuses()
        markers = {
            "done": "OK",
            "active": ">",
            "warn": "!",
            "todo": "-",
        }
        for key, (marker, label) in checklist.items():
            status = statuses.get(key, "todo")
            marker.setText(markers.get(status, "-"))
            for widget in (marker, label):
                widget.setProperty("status", status)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _next_action_checklist_statuses(self) -> dict[str, str]:
        has_source = self.context.transcript._has_open_source()
        has_transcript = self.context.transcript._has_transcript_content()
        transcript_path_edit = self.context.get("_transcript_path_edit", None)
        has_transcript_file = bool(transcript_path_edit is not None and transcript_path_edit.text().strip())
        translator = ""
        translator_combo = self.context.get("_translator_combo", None)
        if translator_combo is not None:
            translator = str(translator_combo.currentData() or "")
        tts = ""
        tts_combo = self.context.get("_tts_provider_combo", None)
        if tts_combo is not None:
            tts = str(tts_combo.currentData() or "")
        return {
            "next_step_source": "done" if has_source else "active",
            "next_step_transcript": (
                "done" if has_transcript else ("active" if has_source or has_transcript_file else "todo")
            ),
            "next_step_translation": (
                "done" if has_transcript and translator != "none" else ("active" if has_transcript else "todo")
            ),
            "next_step_voice": "done" if has_transcript and tts != "none" else ("warn" if has_transcript else "todo"),
            "next_step_export": "active" if has_transcript else "todo",
        }

    def _run_next_action(self, index: int, *, panel_name: str = "nextActionPanel") -> None:
        panel_attr = "_transcript_empty_panel" if panel_name == "transcriptEmptyPanel" else "_next_action_panel"
        panel = self.context.get(panel_attr, None)
        actions = list(getattr(panel, "_next_action_keys", []) or [])
        action_key = actions[index] if 0 <= index < len(actions) else ""
        if not action_key:
            return
        if action_key == "choose_workflow":
            self.context.readiness._select_settings_tab_for_widget(self.context.readiness._readiness_tab_widget)
        elif action_key == "open_video":
            self.context.layout._start_workflow("video", self.context.sources._open_video)
        elif action_key == "open_url":
            self.context.layout._start_workflow("url", self.context.sources._open_video_url)
        elif action_key == "choose_transcript":
            self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "transcript")
            self.context.sources._sync_audio_source_controls()
            self.context.sources._choose_transcript_file()
        elif action_key == "start_dubbing":
            if self.context.layout._dub_button.isChecked():
                self.context.dubbing._start_dubbing()
            else:
                self.context.layout._dub_button.setChecked(True)
                self.context.dubbing._toggle_dubbing(True)
        elif action_key == "open_transcript":
            self.context.readiness._select_settings_tab_for_widget(self.context.bindings._transcript_tab_widget)
        elif action_key == "export":
            self.context.layout._start_workflow("export", self.context.export._show_export_workflow)
        elif action_key == "open_models":
            self.context.readiness._select_settings_tab_for_widget(self.context.bindings._models_tab_widget)
        elif action_key == "open_basic":
            self.context.readiness._select_settings_tab_for_widget(self.context.bindings._basic_tab_widget)
        elif action_key == "open_tasks":
            self.context.readiness._select_settings_tab_for_widget(self.context.task_center._task_center_tab_widget)
        elif action_key == "stop_tasks":
            self.context.task_center._stop_task_center_tasks()
        elif action_key == "retry_task":
            self.context.task_center._retry_task_center_action()
        self.context.transcript._refresh_next_action_panel()

    def _has_open_source(self) -> bool:
        if self.context.get("_document_editor_active", False) or self.context.get("_document_mode", False):
            return True
        if self.context.get("_video_path", None):
            return True
        placeholder = self.context.get("_video_placeholder", None)
        media_stack = self.context.get("_media_stack", None)
        if placeholder is not None and media_stack is not None and media_stack.currentWidget() is placeholder:
            url_getter = getattr(placeholder, "url", None)
            if callable(url_getter):
                url = url_getter().toString()
                return bool(url and url != DEFAULT_MEDIA_HOME_URL)
        return False

    def _has_transcript_content(self) -> bool:
        if self.context.get("_transcript_segments", []):
            return True
        transcript = self.context.get("_transcript", None)
        if transcript is not None and transcript.toPlainText().strip():
            return True
        return False

    def _has_active_background_tasks(self) -> bool:
        try:
            from ai_player.ui.task_center import collect_background_tasks

            return any(task.status == "RUNNING" for task in collect_background_tasks(self.context))
        except Exception:
            return False

    def _selected_transcript_segment_index(self) -> int:
        table = self.context.get("_transcript_segment_table", None)
        if table is None:
            return -1
        row = table.currentRow()
        if row < 0 or row >= len(self.context.transcript._transcript_segments):
            return -1
        return row

    def _sync_transcript_segment_editor(self, index: int | None = None) -> None:
        if index is None:
            index = self.context.transcript._selected_transcript_segment_index()
        source_view = self.context.get("_transcript_segment_source_detail", None)
        target_edit = self.context.get("_transcript_segment_target_edit", None)
        buttons = (
            self.context.get("_transcript_segment_apply_button", None),
            self.context.get("_transcript_segment_review_button", None),
            self.context.get("_transcript_segment_retry_button", None),
        )
        editor = self.context.get("_transcript_segment_editor", None)
        if source_view is None or target_edit is None:
            return
        has_segment = index >= 0 and index < len(self.context.transcript._transcript_segments)
        if editor is not None:
            editor.setVisible(has_segment)
        for widget in (source_view, target_edit, *buttons):
            if widget is not None:
                widget.setEnabled(has_segment)
        if not has_segment:
            source_view.clear()
            target_edit.clear()
            target_edit.setPlaceholderText(self.context.settings._tr("transcript_segment_no_selection"))
            return
        segment = self.context.transcript._normalize_transcript_segment(
            self.context.transcript._transcript_segments[index]
        )
        source = segment.get("source", {}).get("cleaned", "") or segment.get("source", {}).get("raw", "")
        target = segment.get("target", {}).get("cleaned", "") or segment.get("target", {}).get("raw", "")
        source_view.setPlainText(source)
        target_edit.setPlainText(target)
        target_edit.setPlaceholderText(self.context.settings._tr("transcript_segment_target_placeholder"))

    def _apply_transcript_segment_target(self) -> None:
        index = self.context.transcript._selected_transcript_segment_index()
        if index < 0:
            self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_no_selection"))
            return
        segment = self.context.transcript._normalize_transcript_segment(
            self.context.transcript._transcript_segments[index]
        )
        target_edit = self.context.get("_transcript_segment_target_edit", None)
        target = _repair_mojibake(target_edit.toPlainText().strip() if target_edit is not None else "")
        segment["target"] = {"raw": target, "cleaned": target}
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = False
            metadata["retry_requested"] = False
        self.context.transcript._transcript_segments[index] = segment
        self.context.transcript._render_transcript()
        self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_applied"))

    def _mark_transcript_segment_reviewed(self) -> None:
        index = self.context.transcript._selected_transcript_segment_index()
        if index < 0:
            self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_no_selection"))
            return
        segment = self.context.transcript._normalize_transcript_segment(
            self.context.transcript._transcript_segments[index]
        )
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = True
            metadata["retry_requested"] = False
        self.context.transcript._transcript_segments[index] = segment
        self.context.transcript._render_transcript()
        self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_reviewed"))

    def _retry_transcript_segment(self) -> None:
        index = self.context.transcript._selected_transcript_segment_index()
        if index < 0:
            self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_no_selection"))
            return
        segment = self.context.transcript._normalize_transcript_segment(
            self.context.transcript._transcript_segments[index]
        )
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = False
            metadata["retry_requested"] = True
        self.context.transcript._transcript_segments[index] = segment
        self.context.transcript._render_transcript()
        self.context.window.statusBar().showMessage(self.context.settings._tr("transcript_segment_retry_marked"))

    def _transcript_text(self, show_mode: str, type_mode: str | None = None) -> str:
        show_mode = self.context.transcript._normalize_transcript_view(show_mode)
        type_mode = self.context.transcript._normalize_transcript_type(type_mode)
        blocks: list[str] = []
        for label, text, _role in self.context.transcript._transcript_blocks(show_mode, type_mode):
            text = _repair_mojibake(text).strip()
            if not text:
                continue
            if label:
                blocks.append(f"{label}: {text}")
            else:
                blocks.append(text)
        return "\n\n".join(blocks).strip()

    def _transcript_html(self, show_mode: str, type_mode: str | None = None) -> str:
        show_mode = self.context.transcript._normalize_transcript_view(show_mode)
        type_mode = self.context.transcript._normalize_transcript_type(type_mode)
        blocks: list[str] = []
        for label, text, role in self.context.transcript._transcript_blocks(show_mode, type_mode):
            text = _repair_mojibake(text).strip()
            if not text:
                continue
            if label:
                blocks.append(self.context.transcript._transcript_labeled_line_html(label, text, role))
            else:
                blocks.append(self.context.transcript._transcript_line_html(text, role))
        body = "".join(blocks).strip()
        if not body:
            return ""
        return f"<div style='font-family: Segoe UI, Arial; font-size: 10pt; line-height: 1.45;'>{body}</div>"

    def _transcript_blocks(self, show_mode: str, type_mode: str) -> list[tuple[str, str, str]]:
        show_mode = self.context.transcript._normalize_transcript_view(show_mode)
        type_mode = self.context.transcript._normalize_transcript_type(type_mode)
        if show_mode == "off" or type_mode == "off":
            return []
        show_items = ["source", "target"] if show_mode == "all" else [show_mode]
        type_items = ["raw", "cleaned"] if type_mode == "all" else [type_mode]
        needs_label = len(show_items) > 1 or len(type_items) > 1
        blocks: list[tuple[str, str, str]] = []
        for segment in self.context.transcript._transcript_segments:
            normalized = self.context.transcript._normalize_transcript_segment(segment)
            for show in show_items:
                for transcript_type in type_items:
                    text = normalized.get(show, {}).get(transcript_type, "")
                    label = (
                        self.context.transcript._transcript_block_label(show, transcript_type) if needs_label else ""
                    )
                    blocks.append((label, text, transcript_type))
        return blocks

    @staticmethod
    def _make_transcript_segment(source_text: str, target_text: str) -> dict[str, dict[str, str] | dict[str, bool]]:
        source = _repair_mojibake(str(source_text or "").strip())
        target = _repair_mojibake(str(target_text or "").strip())
        return {
            "source": {"raw": source, "cleaned": source},
            "target": {"raw": target, "cleaned": target},
            "metadata": {"reviewed": False, "retry_requested": False},
        }

    @staticmethod
    def _normalize_transcript_segment(segment) -> dict[str, dict]:
        if isinstance(segment, dict):
            source = segment.get("source", {})
            target = segment.get("target", {})
            metadata = segment.get("metadata", {})
            if not isinstance(source, dict):
                source = {"raw": str(source or ""), "cleaned": str(source or "")}
            if not isinstance(target, dict):
                target = {"raw": str(target or ""), "cleaned": str(target or "")}
            if not isinstance(metadata, dict):
                metadata = {}
            source_raw = _repair_mojibake(str(source.get("raw") or source.get("cleaned") or "").strip())
            source_cleaned = _repair_mojibake(str(source.get("cleaned") or source_raw).strip())
            target_raw = _repair_mojibake(str(target.get("raw") or target.get("cleaned") or "").strip())
            target_cleaned = _repair_mojibake(str(target.get("cleaned") or target_raw).strip())
            return {
                "source": {"raw": source_raw, "cleaned": source_cleaned},
                "target": {"raw": target_raw, "cleaned": target_cleaned},
                "metadata": {
                    "reviewed": bool(metadata.get("reviewed", False)),
                    "retry_requested": bool(metadata.get("retry_requested", False)),
                },
            }
        try:
            source_text, target_text = segment
        except Exception:
            source_text, target_text = str(segment or ""), ""
        return PlayerTranscriptFeature._make_transcript_segment(source_text, target_text)

    def _transcript_block_label(self, show_mode: str, type_mode: str) -> str:
        show_labels = {
            "source": self.context.settings._tr("transcript_label_source"),
            "target": self.context.settings._tr("transcript_label_target"),
        }
        type_labels = {
            "raw": self.context.settings._tr("transcript_label_raw"),
            "cleaned": self.context.settings._tr("transcript_label_cleaned"),
        }
        return f"{show_labels.get(show_mode, show_mode)} - {type_labels.get(type_mode, type_mode)}"

    @staticmethod
    def _transcript_line_html(text: str, role: str) -> str:
        from ai_player.resources.themes.python_theme import values

        theme = values()
        color = theme["info"] if role == "raw" else theme["success"]
        return f"<div style='color: {color}; margin: 0 0 10px 0;'>{_html_with_breaks(text)}</div>"

    @staticmethod
    def _transcript_labeled_line_html(label: str, text: str, role: str) -> str:
        from ai_player.resources.themes.python_theme import values

        theme = values()
        color = theme["info"] if role == "raw" else theme["success"]
        return (
            f"<div style='color: {color}; margin-bottom: 4px;'>"
            f"<span style='font-weight: 700;'>{html.escape(label)}:</span> "
            f"<span>{_html_with_breaks(text)}</span>"
            "</div>"
        )

    @staticmethod
    def _normalize_transcript_view(value: object) -> str:
        mode = str(value or "all").strip().lower()
        aliases = {
            "off": "off",
            "none": "off",
            "hidden": "off",
            "source": "source",
            "raw_source": "source",
            "target": "target",
            "cleaned_target": "target",
            "all": "all",
        }
        return aliases.get(mode, "all")

    @staticmethod
    def _normalize_transcript_type(value: object) -> str:
        mode = str(value or "all").strip().lower()
        aliases = {
            "off": "off",
            "none": "off",
            "hidden": "off",
            "raw": "raw",
            "source": "raw",
            "cleaned": "cleaned",
            "fixed": "cleaned",
            "target": "cleaned",
            "all": "all",
        }
        return aliases.get(mode, "all")

    def _export_transcript(self) -> None:
        text = self.context.transcript._transcript_text(
            self.context.transcript._selected_transcript_view(), self.context.transcript._selected_transcript_type()
        )
        if not text:
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_no_transcript_export"),
            )
            return
        output, _ = QFileDialog.getSaveFileName(
            self.context.window,
            self.context.settings._tr("export_transcript"),
            str(Path.home() / "ai-player-transcript.txt"),
            self.context.settings._tr("file_filter_text_file"),
        )
        if not output:
            return
        path = Path(output)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_exported_transcript").format(path=path)
        )
