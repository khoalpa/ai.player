from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

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

    def _clear_transcript(self) -> None:
        self._transcript_segments.clear()
        if hasattr(self, "_transcript"):
            self._transcript.clear()

    def _set_transcript_text(self, text: str, *, source_only: bool = True) -> None:
        clean = _repair_mojibake(str(text or "").strip())
        if clean:
            target = "" if source_only else clean
            self._transcript_segments = [self._make_transcript_segment(clean, target)]
        else:
            self._transcript_segments = []
        self._render_transcript()

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
    def _make_transcript_segment(source_text: str, target_text: str) -> dict[str, dict[str, str]]:
        source = _repair_mojibake(str(source_text or "").strip())
        target = _repair_mojibake(str(target_text or "").strip())
        return {
            "source": {"raw": source, "cleaned": source},
            "target": {"raw": target, "cleaned": target},
        }

    @staticmethod
    def _normalize_transcript_segment(segment) -> dict[str, dict[str, str]]:
        if isinstance(segment, dict):
            source = segment.get("source", {})
            target = segment.get("target", {})
            if not isinstance(source, dict):
                source = {"raw": str(source or ""), "cleaned": str(source or "")}
            if not isinstance(target, dict):
                target = {"raw": str(target or ""), "cleaned": str(target or "")}
            source_raw = _repair_mojibake(str(source.get("raw") or source.get("cleaned") or "").strip())
            source_cleaned = _repair_mojibake(str(source.get("cleaned") or source_raw).strip())
            target_raw = _repair_mojibake(str(target.get("raw") or target.get("cleaned") or "").strip())
            target_cleaned = _repair_mojibake(str(target.get("cleaned") or target_raw).strip())
            return {
                "source": {"raw": source_raw, "cleaned": source_cleaned},
                "target": {"raw": target_raw, "cleaned": target_cleaned},
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
