from __future__ import annotations

from ai_player.ui.cache_progress_dialog import CacheProgressDialog, _format_bytes, _format_seconds
from ai_player.ui.features.base import Feature


class PlayerSourceProgressFeature(Feature):
    def _effective_video_url_full_cache(self) -> bool:
        if self.context.settings._selected_video_url_full_cache():
            return True
        return self.context.has("_source_filter_check") and self.context.layout._source_filter_check.isChecked()

    def _source_filter_forces_video_url_full_cache(self) -> bool:
        return (
            not self.context.settings._selected_video_url_full_cache()
            and self.context.has("_source_filter_check")
            and self.context.layout._source_filter_check.isChecked()
        )

    def _video_cache_progress_changed(self, data) -> None:
        self.context.source_progress._update_inline_cache_status(data)
        self.context.source_progress._show_cache_dialog(
            cancel_callback=self.context.source_progress._cancel_video_url_open
        )
        if isinstance(data, dict):
            self.context.media.playback.cache_dialog.update_cache(data)
            status = str(data.get("status") or "")
            if status in {"downloading", "starting"}:
                provider = data.get("provider") or ""
                quality = data.get("quality") or ""
                self.context.source_progress._set_download_background_detail(
                    "URL/cache loading",
                    f"{provider} {quality}",
                    show_status=True,
                )
            if status in {"finished", "cached"}:
                self.context.source_progress._set_cache_play_now_enabled(False)

    def _telegram_download_progress_changed(self, data) -> None:
        worker = self.context.get("_telegram_worker", None)
        if (
            worker is not None
            and getattr(worker, "operation", "") == "download"
            and getattr(worker, "_stop_requested", False)
        ):
            return
        self.context.source_progress._show_cache_dialog(
            cancel_callback=self.context.source_progress._cancel_telegram_download
        )
        if isinstance(data, dict):
            progress = {"provider": "telegram", **data}
        else:
            progress = {"provider": "telegram", "status": "downloading", "filename": str(data or "")}
        self.context.media.playback.cache_dialog.update_cache(progress)
        filename = str(progress.get("filename") or progress.get("provider") or "").strip()
        self.context.source_progress._set_download_background_detail("Telegram", filename)

    def _set_download_background_detail(self, task_name: str, detail: object, *, show_status: bool = False) -> None:
        message = f"{self.context.settings._tr('cache_status_downloading')} {detail}".strip()
        self.context.runtime._set_background_task_detail(task_name, message)
        if show_status:
            self.context.window.statusBar().showMessage(message)

    def _show_cache_dialog(self, *, cancel_callback=None) -> None:
        if self.context.media.playback.cache_dialog is None:
            dialog = CacheProgressDialog(self.context.settings._ui_language(), self.context.window)
            self.context.media.playback.cache_dialog = dialog
            if callable(cancel_callback):
                dialog.rejected.connect(cancel_callback)
            dialog.finished.connect(
                lambda _result, dialog=dialog: self.context.source_progress._cache_dialog_finished(dialog)
            )
            dialog.show()
            dialog.raise_()

    def _cache_dialog_finished(self, dialog) -> None:
        if self.context.media.playback.cache_dialog is dialog:
            self.context.media.playback.cache_dialog = None

    def _close_cache_dialog(self) -> None:
        if self.context.media.playback.cache_dialog is not None:
            self.context.media.playback.cache_dialog.accept()
            self.context.media.playback.cache_dialog = None

    def _cancel_telegram_download(self) -> None:
        worker = self.context.get("_telegram_worker", None)
        if worker is None or getattr(worker, "operation", "") != "download":
            return
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        self.context.sources.channel.loading_item_key = ""
        self.context.media.playback.cache_dialog = None
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_channel_cancelled"))

    def _cancel_video_url_open(self) -> None:
        if not self.context.sources._url_is_opening():
            return
        self.context.sources._stop_video_url(wait_ms=1000)
        self.context.media.playback.cache_dialog = None
        self.context.source_progress._set_cache_status_visible(False)
        self.context.window.statusBar().showMessage(self.context.settings._tr("video_error_open_cancelled"))

    def _update_inline_cache_status(self, data) -> None:
        if not isinstance(data, dict):
            return
        self.context.source_progress._set_cache_status_visible(True)
        downloaded = _numeric_value(data.get("downloaded_bytes"))
        total = _numeric_value(data.get("total_bytes"))
        percent = int(downloaded * 100 / total) if downloaded is not None and total else 0
        percent = max(0, min(100, percent))
        progress = self.context.get("_cache_status_progress", None)
        if progress is not None:
            if total:
                progress.setRange(0, 100)
                progress.setValue(percent)
            else:
                progress.setRange(0, 0)
        label = self.context.get("_cache_status_label", None)
        if label is not None:
            status = str(data.get("status") or "starting")
            pieces = [self.context.settings._tr(f"cache_status_{status}")]
            if downloaded is not None:
                size_text = _format_bytes(downloaded)
                if total:
                    size_text += f" / {_format_bytes(total)} ({percent}%)"
                pieces.append(size_text)
            speed = _numeric_value(data.get("speed"))
            if speed:
                pieces.append(f"{self.context.settings._tr('cache_speed')}: {_format_bytes(speed)}/s")
            eta = _numeric_value(data.get("eta"))
            if eta is not None:
                pieces.append(f"{self.context.settings._tr('cache_eta')}: {_format_seconds(eta)}")
            label.setText(" | ".join(pieces))

    def _set_cache_status_visible(self, visible: bool) -> None:
        panel = self.context.get("_cache_status_panel", None)
        if panel is not None:
            panel.setVisible(bool(visible))

    def _set_cache_play_now_enabled(self, enabled: bool) -> None:
        button = self.context.get("_cache_play_now_button", None)
        if button is not None:
            button.setEnabled(bool(enabled))


def _numeric_value(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
