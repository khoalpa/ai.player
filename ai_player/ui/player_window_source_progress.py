from __future__ import annotations

from ai_player.ui.cache_progress_dialog import CacheProgressDialog


class PlayerSourceProgressMixin:
    def _effective_video_url_full_cache(self) -> bool:
        if self._selected_video_url_full_cache():
            return True
        return hasattr(self, "_source_filter_check") and self._source_filter_check.isChecked()

    def _source_filter_forces_video_url_full_cache(self) -> bool:
        return (
            not self._selected_video_url_full_cache()
            and hasattr(self, "_source_filter_check")
            and self._source_filter_check.isChecked()
        )

    def _video_cache_progress_changed(self, data) -> None:
        self._show_cache_dialog(cancel_callback=self._cancel_video_url_open)
        if isinstance(data, dict):
            self._cache_dialog.update_cache(data)
            status = str(data.get("status") or "")
            if status in {"downloading", "starting"}:
                provider = data.get("provider") or ""
                quality = data.get("quality") or ""
                self._set_download_background_detail(
                    "URL/cache loading",
                    f"{provider} {quality}",
                    show_status=True,
                )

    def _telegram_download_progress_changed(self, data) -> None:
        worker = getattr(self, "_telegram_worker", None)
        if (
            worker is not None
            and getattr(worker, "operation", "") == "download"
            and getattr(worker, "_stop_requested", False)
        ):
            return
        self._show_cache_dialog(cancel_callback=self._cancel_telegram_download)
        if isinstance(data, dict):
            progress = {"provider": "telegram", **data}
        else:
            progress = {"provider": "telegram", "status": "downloading", "filename": str(data or "")}
        self._cache_dialog.update_cache(progress)
        filename = str(progress.get("filename") or progress.get("provider") or "").strip()
        self._set_download_background_detail("Telegram", filename)

    def _set_download_background_detail(self, task_name: str, detail: object, *, show_status: bool = False) -> None:
        message = f"{self._tr('cache_status_downloading')} {detail}".strip()
        self._set_background_task_detail(task_name, message)
        if show_status:
            self.statusBar().showMessage(message)

    def _show_cache_dialog(self, *, cancel_callback=None) -> None:
        if self._cache_dialog is None:
            dialog = CacheProgressDialog(self._ui_language(), self)
            self._cache_dialog = dialog
            if callable(cancel_callback):
                dialog.rejected.connect(cancel_callback)
            dialog.finished.connect(lambda _result, dialog=dialog: self._cache_dialog_finished(dialog))
            dialog.show()
            dialog.raise_()

    def _cache_dialog_finished(self, dialog) -> None:
        if self._cache_dialog is dialog:
            self._cache_dialog = None

    def _close_cache_dialog(self) -> None:
        if self._cache_dialog is not None:
            self._cache_dialog.accept()
            self._cache_dialog = None

    def _cancel_telegram_download(self) -> None:
        worker = getattr(self, "_telegram_worker", None)
        if worker is None or getattr(worker, "operation", "") != "download":
            return
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        self._telegram_channel_state.loading_item_key = ""
        self._cache_dialog = None
        self.statusBar().showMessage(self._tr("status_telegram_channel_cancelled"))

    def _cancel_video_url_open(self) -> None:
        if not self._url_is_opening():
            return
        self._stop_video_url(wait_ms=1000)
        self._cache_dialog = None
        self.statusBar().showMessage(self._tr("video_error_open_cancelled"))
