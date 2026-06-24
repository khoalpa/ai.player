from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from ai_player.ui.player_window_media_browser import DEFAULT_MEDIA_HOME_URL
from ai_player.ui.player_window_utils import (
    html_with_breaks as _html_with_breaks,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)


class PlayerTranscriptMixin:
    def _append_segment(self, original: str, translated: str) -> None:
        self._append_dubbing_segment(original, translated)
        self._set_live_subtitle(original, translated)

    def _append_dubbing_segment(self, original: str, translated: str) -> None:
        self._transcript_segments.append(self._make_transcript_segment(original, translated))
        self._render_transcript()

    def _selected_transcript_view(self) -> str:
        if not hasattr(self, "_transcript_view_combo"):
            return "all"
        return self._normalize_transcript_view(self._transcript_view_combo.currentData())

    def _selected_transcript_type(self) -> str:
        if not hasattr(self, "_transcript_type_combo"):
            return "all"
        return self._normalize_transcript_type(self._transcript_type_combo.currentData())

    def _render_transcript(self, *_args) -> None:
        if hasattr(self, "_transcript"):
            self._transcript.setHtml(
                self._transcript_html(self._selected_transcript_view(), self._selected_transcript_type())
            )
        self._refresh_transcript_segment_table()
        self._refresh_next_action_panel()

    def _clear_transcript(self) -> None:
        self._transcript_segments.clear()
        if hasattr(self, "_transcript"):
            self._transcript.clear()
        self._refresh_transcript_segment_table()
        self._refresh_next_action_panel()

    def _set_transcript_text(self, text: str, *, source_only: bool = True) -> None:
        clean = _repair_mojibake(str(text or "").strip())
        if clean:
            target = "" if source_only else clean
            self._transcript_segments = [self._make_transcript_segment(clean, target)]
        else:
            self._transcript_segments = []
        self._render_transcript()

    def _refresh_transcript_segment_table(self) -> None:
        table = getattr(self, "_transcript_segment_table", None)
        if table is None:
            return
        self._refresh_transcript_status_strip()
        selected_row = table.currentRow()
        has_segments = bool(self._transcript_segments)
        table.setVisible(has_segments)
        table.setRowCount(len(self._transcript_segments))
        if not self._transcript_segments:
            self._sync_transcript_segment_editor(-1)
            self._sync_transcript_segment_banner()
            self._refresh_transcript_empty_state()
            return
        for row, segment in enumerate(self._transcript_segments):
            normalized = self._normalize_transcript_segment(segment)
            source = normalized.get("source", {}).get("cleaned", "") or normalized.get("source", {}).get("raw", "")
            target = normalized.get("target", {}).get("cleaned", "") or normalized.get("target", {}).get("raw", "")
            status = self._transcript_segment_status(normalized, target)
            self._set_transcript_segment_row(row, str(row + 1), source, target, status)
        if selected_row < 0 or selected_row >= len(self._transcript_segments):
            selected_row = 0
        table.selectRow(selected_row)
        table.resizeRowsToContents()
        self._sync_transcript_segment_editor(selected_row)
        self._sync_transcript_segment_banner()
        self._refresh_transcript_empty_state()

    def _set_transcript_segment_row(self, row: int, index: str, source: str, target: str, status: str) -> None:
        table = getattr(self, "_transcript_segment_table", None)
        if table is None:
            return
        content_lines = []
        if source:
            content_lines.append(f"{self._tr('transcript_label_source')}: {source}")
        if target:
            content_lines.append(f"{self._tr('transcript_label_target')}: {target}")
        content = "\n".join(content_lines) or self._tr("transcript_segment_empty")
        for column, value in enumerate((index, content, status)):
            item = QTableWidgetItem(_repair_mojibake(str(value or "")))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)

    def _refresh_transcript_status_strip(self) -> None:
        labels = getattr(self, "_transcript_status_labels", None)
        if not labels:
            return
        segments = [self._normalize_transcript_segment(segment) for segment in self._transcript_segments]
        total_count = len(segments)
        translated_count = sum(
            1
            for segment in segments
            if (segment.get("target", {}).get("cleaned", "") or segment.get("target", {}).get("raw", "")).strip()
        )
        retry_count = sum(1 for segment in segments if segment.get("metadata", {}).get("retry_requested"))
        state_key = "transcript_status_state_ready" if total_count else "transcript_status_state_empty"
        values = {
            "transcript_status_total": (self._tr("transcript_status_total").format(count=total_count), "ok"),
            "transcript_status_translated": (
                self._tr("transcript_status_translated").format(count=translated_count),
                "ok" if translated_count else "muted",
            ),
            "transcript_status_retry": (
                self._tr("transcript_status_retry").format(count=retry_count),
                "warn" if retry_count else "muted",
            ),
            "transcript_status_state_empty": (
                self._tr(state_key).format(count=total_count),
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
            return self._tr("transcript_segment_retry_needed")
        if isinstance(metadata, dict) and metadata.get("reviewed"):
            return self._tr("transcript_segment_reviewed")
        return self._tr("transcript_segment_ready") if target else self._tr("transcript_segment_source_only")

    def _transcript_segment_selection_changed(self) -> None:
        self._sync_transcript_segment_editor(self._selected_transcript_segment_index())

    def _sync_transcript_segment_banner(self) -> None:
        banner = getattr(self, "_transcript_segment_banner", None)
        if banner is None:
            return
        if not self._transcript_segments:
            banner.setVisible(False)
            return
        retry_count = sum(
            1
            for segment in self._transcript_segments
            if self._normalize_transcript_segment(segment).get("metadata", {}).get("retry_requested")
        )
        if retry_count:
            banner.setText(self._tr("transcript_segment_retry_banner").format(count=retry_count))
            banner.setVisible(True)
            return
        banner.setVisible(False)

    def _refresh_next_action_panel(self) -> None:
        panel = getattr(self, "_next_action_panel", None)
        if panel is None:
            return
        state = self._next_action_state()
        self._apply_next_action_state(panel, state)
        self._refresh_transcript_empty_state()

    def _refresh_transcript_empty_state(self, state: dict[str, object] | None = None) -> None:
        panel = getattr(self, "_transcript_empty_panel", None)
        if panel is None:
            return
        has_segments = bool(getattr(self, "_transcript_segments", []))
        panel.setVisible(not has_segments)
        if has_segments:
            return
        self._apply_next_action_state(panel, state or self._next_action_state(transcript_empty=True))

    def _next_action_state(self, *, transcript_empty: bool = False) -> dict[str, object]:
        if self._has_active_background_tasks():
            return {
                "title": "next_action_task_title",
                "detail": "next_action_task_detail",
                "actions": ["open_tasks"],
            }
        has_source = self._has_open_source()
        has_transcript = self._has_transcript_content()
        transcript_path_edit = getattr(self, "_transcript_path_edit", None)
        has_transcript_file = bool(transcript_path_edit is not None and transcript_path_edit.text().strip())
        if not has_source:
            return {
                "title": "next_action_no_source_title",
                "detail": "next_action_no_source_detail",
                "actions": ["choose_workflow"],
            }
        if getattr(self, "_document_editor_active", False):
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
            title.setText(self._tr(str(state.get("title") or "next_action_title")))
        if detail is not None:
            detail.setText(self._tr(str(state.get("detail") or "next_action_no_source_detail")))
        action_keys = [str(action or "") for action in list(state.get("actions") or [])[: len(buttons)]]
        panel._next_action_keys = action_keys
        for index, button in enumerate(buttons):
            action_key = action_keys[index] if index < len(action_keys) else ""
            if not action_key:
                button.hide()
                continue
            button.setText(self._tr(f"next_action_button_{action_key}"))
            button.setToolTip(self._tr(f"next_action_button_{action_key}"))
            button.show()

    def _run_next_action(self, index: int, *, panel_name: str = "nextActionPanel") -> None:
        panel_attr = "_transcript_empty_panel" if panel_name == "transcriptEmptyPanel" else "_next_action_panel"
        panel = getattr(self, panel_attr, None)
        actions = list(getattr(panel, "_next_action_keys", []) or [])
        action_key = actions[index] if 0 <= index < len(actions) else ""
        if not action_key:
            return
        if action_key == "choose_workflow":
            self._select_settings_tab_for_widget(self._readiness_tab_widget)
        elif action_key == "open_video":
            self._start_workflow("video", self._open_video)
        elif action_key == "open_url":
            self._start_workflow("url", self._open_video_url)
        elif action_key == "choose_transcript":
            self._set_combo_data(self._audio_source_combo, "transcript")
            self._sync_audio_source_controls()
            self._choose_transcript_file()
        elif action_key == "start_dubbing":
            if self._dub_button.isChecked():
                self._start_dubbing()
            else:
                self._dub_button.setChecked(True)
        elif action_key == "open_transcript":
            self._select_settings_tab_for_widget(self._transcript_tab_widget)
        elif action_key == "export":
            self._start_workflow("export", self._show_export_workflow)
        elif action_key == "open_models":
            self._select_settings_tab_for_widget(self._models_tab_widget)
        elif action_key == "open_basic":
            self._select_settings_tab_for_widget(self._basic_tab_widget)
        elif action_key == "open_tasks":
            self._select_settings_tab_for_widget(self._task_center_tab_widget)
        elif action_key == "stop_tasks":
            self._stop_task_center_tasks()
        elif action_key == "retry_task":
            self._retry_task_center_action()
        self._refresh_next_action_panel()

    def _has_open_source(self) -> bool:
        if getattr(self, "_document_editor_active", False) or getattr(self, "_document_mode", False):
            return True
        if getattr(self, "_video_path", None):
            return True
        placeholder = getattr(self, "_video_placeholder", None)
        media_stack = getattr(self, "_media_stack", None)
        if placeholder is not None and media_stack is not None and media_stack.currentWidget() is placeholder:
            url_getter = getattr(placeholder, "url", None)
            if callable(url_getter):
                url = url_getter().toString()
                return bool(url and url != DEFAULT_MEDIA_HOME_URL)
        return False

    def _has_transcript_content(self) -> bool:
        if getattr(self, "_transcript_segments", []):
            return True
        transcript = getattr(self, "_transcript", None)
        if transcript is not None and transcript.toPlainText().strip():
            return True
        return False

    def _has_active_background_tasks(self) -> bool:
        try:
            from ai_player.ui.task_center import collect_background_tasks

            return any(task.status == "RUNNING" for task in collect_background_tasks(self))
        except Exception:
            return False

    def _selected_transcript_segment_index(self) -> int:
        table = getattr(self, "_transcript_segment_table", None)
        if table is None:
            return -1
        row = table.currentRow()
        if row < 0 or row >= len(self._transcript_segments):
            return -1
        return row

    def _sync_transcript_segment_editor(self, index: int | None = None) -> None:
        if index is None:
            index = self._selected_transcript_segment_index()
        source_view = getattr(self, "_transcript_segment_source_detail", None)
        target_edit = getattr(self, "_transcript_segment_target_edit", None)
        buttons = (
            getattr(self, "_transcript_segment_apply_button", None),
            getattr(self, "_transcript_segment_review_button", None),
            getattr(self, "_transcript_segment_retry_button", None),
        )
        editor = getattr(self, "_transcript_segment_editor", None)
        if source_view is None or target_edit is None:
            return
        has_segment = index >= 0 and index < len(self._transcript_segments)
        if editor is not None:
            editor.setVisible(has_segment)
        for widget in (source_view, target_edit, *buttons):
            if widget is not None:
                widget.setEnabled(has_segment)
        if not has_segment:
            source_view.clear()
            target_edit.clear()
            target_edit.setPlaceholderText(self._tr("transcript_segment_no_selection"))
            return
        segment = self._normalize_transcript_segment(self._transcript_segments[index])
        source = segment.get("source", {}).get("cleaned", "") or segment.get("source", {}).get("raw", "")
        target = segment.get("target", {}).get("cleaned", "") or segment.get("target", {}).get("raw", "")
        source_view.setPlainText(source)
        target_edit.setPlainText(target)
        target_edit.setPlaceholderText(self._tr("transcript_segment_target_placeholder"))

    def _apply_transcript_segment_target(self) -> None:
        index = self._selected_transcript_segment_index()
        if index < 0:
            self.statusBar().showMessage(self._tr("transcript_segment_no_selection"))
            return
        segment = self._normalize_transcript_segment(self._transcript_segments[index])
        target_edit = getattr(self, "_transcript_segment_target_edit", None)
        target = _repair_mojibake(target_edit.toPlainText().strip() if target_edit is not None else "")
        segment["target"] = {"raw": target, "cleaned": target}
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = False
            metadata["retry_requested"] = False
        self._transcript_segments[index] = segment
        self._render_transcript()
        self.statusBar().showMessage(self._tr("transcript_segment_applied"))

    def _mark_transcript_segment_reviewed(self) -> None:
        index = self._selected_transcript_segment_index()
        if index < 0:
            self.statusBar().showMessage(self._tr("transcript_segment_no_selection"))
            return
        segment = self._normalize_transcript_segment(self._transcript_segments[index])
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = True
            metadata["retry_requested"] = False
        self._transcript_segments[index] = segment
        self._render_transcript()
        self.statusBar().showMessage(self._tr("transcript_segment_reviewed"))

    def _retry_transcript_segment(self) -> None:
        index = self._selected_transcript_segment_index()
        if index < 0:
            self.statusBar().showMessage(self._tr("transcript_segment_no_selection"))
            return
        segment = self._normalize_transcript_segment(self._transcript_segments[index])
        metadata = segment.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["reviewed"] = False
            metadata["retry_requested"] = True
        self._transcript_segments[index] = segment
        self._render_transcript()
        self.statusBar().showMessage(self._tr("transcript_segment_retry_marked"))

    def _transcript_text(self, show_mode: str, type_mode: str | None = None) -> str:
        show_mode = self._normalize_transcript_view(show_mode)
        type_mode = self._normalize_transcript_type(type_mode)
        blocks: list[str] = []
        for label, text, _role in self._transcript_blocks(show_mode, type_mode):
            text = _repair_mojibake(text).strip()
            if not text:
                continue
            if label:
                blocks.append(f"{label}: {text}")
            else:
                blocks.append(text)
        return "\n\n".join(blocks).strip()

    def _transcript_html(self, show_mode: str, type_mode: str | None = None) -> str:
        show_mode = self._normalize_transcript_view(show_mode)
        type_mode = self._normalize_transcript_type(type_mode)
        blocks: list[str] = []
        for label, text, role in self._transcript_blocks(show_mode, type_mode):
            text = _repair_mojibake(text).strip()
            if not text:
                continue
            if label:
                blocks.append(self._transcript_labeled_line_html(label, text, role))
            else:
                blocks.append(self._transcript_line_html(text, role))
        body = "".join(blocks).strip()
        if not body:
            return ""
        return f"<div style='font-family: Segoe UI, Arial; font-size: 10pt; line-height: 1.45;'>{body}</div>"

    def _transcript_blocks(self, show_mode: str, type_mode: str) -> list[tuple[str, str, str]]:
        show_mode = self._normalize_transcript_view(show_mode)
        type_mode = self._normalize_transcript_type(type_mode)
        if show_mode == "off" or type_mode == "off":
            return []
        show_items = ["source", "target"] if show_mode == "all" else [show_mode]
        type_items = ["raw", "cleaned"] if type_mode == "all" else [type_mode]
        needs_label = len(show_items) > 1 or len(type_items) > 1
        blocks: list[tuple[str, str, str]] = []
        for segment in self._transcript_segments:
            normalized = self._normalize_transcript_segment(segment)
            for show in show_items:
                for transcript_type in type_items:
                    text = normalized.get(show, {}).get(transcript_type, "")
                    label = self._transcript_block_label(show, transcript_type) if needs_label else ""
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
        return PlayerTranscriptMixin._make_transcript_segment(source_text, target_text)

    def _transcript_block_label(self, show_mode: str, type_mode: str) -> str:
        show_labels = {"source": self._tr("transcript_label_source"), "target": self._tr("transcript_label_target")}
        type_labels = {"raw": self._tr("transcript_label_raw"), "cleaned": self._tr("transcript_label_cleaned")}
        return f"{show_labels.get(show_mode, show_mode)} - {type_labels.get(type_mode, type_mode)}"

    @staticmethod
    def _transcript_line_html(text: str, role: str) -> str:
        color = "#1d4ed8" if role == "raw" else "#15803d"
        return f"<div style='color: {color}; margin: 0 0 10px 0;'>{_html_with_breaks(text)}</div>"

    @staticmethod
    def _transcript_labeled_line_html(label: str, text: str, role: str) -> str:
        color = "#1d4ed8" if role == "raw" else "#15803d"
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
        text = self._transcript_text(self._selected_transcript_view(), self._selected_transcript_type())
        if not text:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_no_transcript_export"))
            return
        output, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("export_transcript"),
            str(Path.home() / "ai-player-transcript.txt"),
            self._tr("file_filter_text_file"),
        )
        if not output:
            return
        path = Path(output)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        self.statusBar().showMessage(self._tr("status_exported_transcript").format(path=path))
