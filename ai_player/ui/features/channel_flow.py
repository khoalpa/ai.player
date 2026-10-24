from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ai_player.adapters.sources.telegram_channel import (
    TelegramLoginConfig,
    is_private_telegram_url,
    load_telegram_login_config,
    telegram_private_available,
)
from ai_player.ui.features.base import Feature
from ai_player.workers.player_window_workers import TelegramChannelWorker


class PlayerChannelFlowFeature(Feature):
    def _start_telegram_channel_flow(self, url: str) -> None:
        if self.context.sources._telegram_is_busy():
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_url_opening"),
            )
            return
        self.context.channel_flow._telegram_channel_provider = "telegram"
        self.context.lifecycle.workers.pending_telegram_url = url
        self.context.sources.channel.pending_post_id = self.context.sources._telegram_post_id_from_url(url)
        self.context.settings._queue_save_settings()
        self.context.channel_browser._show_telegram_channel_browser(
            url, self.context.settings._tr("telegram_channel_browser_loading")
        )
        if is_private_telegram_url(url):
            self.context.channel_flow._start_private_telegram_channel_flow(url)
            return
        self.context.channel_flow._start_telegram_worker(
            "list_public", url=url, status_key="status_telegram_channel_loading"
        )

    def _start_youtube_channel_flow(self, url: str) -> None:
        if self.context.sources._telegram_is_busy():
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_url_opening"),
            )
            return
        self.context.channel_flow._telegram_channel_provider = "youtube"
        self.context.lifecycle.workers.pending_telegram_url = url
        self.context.sources.channel.pending_post_id = self.context.sources._youtube_video_id_from_url(url)
        self.context.settings._queue_save_settings()
        self.context.channel_browser._show_telegram_channel_browser(
            url, self.context.settings._tr("youtube_channel_browser_loading")
        )
        self.context.channel_flow._start_telegram_worker(
            "list_youtube", url=url, status_key="status_youtube_channel_loading"
        )

    def _start_private_telegram_channel_flow(self, url: str) -> None:
        if not telegram_private_available():
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("open_url_error_title"),
                self.context.settings._tr("telegram_login_private_unavailable"),
            )
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_url_failed"))
            return
        config = load_telegram_login_config()
        if config is None:
            config = self.context.sources._telegram_login_config_dialog()
            if config is None:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("status_telegram_login_cancelled")
                )
                return
            self.context.channel_flow._start_telegram_worker(
                "start_login", config=config, status_key="status_telegram_login_starting"
            )
            return
        self.context.channel_flow._start_telegram_worker(
            "list_authenticated",
            url=url,
            config=config,
            status_key="status_telegram_channel_loading_auth",
        )

    def _start_telegram_worker(
        self,
        operation: str,
        *,
        url: str = "",
        config: TelegramLoginConfig | None = None,
        login_request=None,
        code: str = "",
        password: str = "",
        post_id: str = "",
        before_post_id: str = "",
        search: str = "",
        status_key: str = "",
        status_text: str = "",
    ) -> None:
        self.context.sources._set_telegram_opening_controls(False, keep_browser_tools=operation == "download")
        if status_text:
            self.context.window.statusBar().showMessage(status_text)
        elif status_key:
            self.context.window.statusBar().showMessage(self.context.settings._tr(status_key))
        worker = TelegramChannelWorker(
            operation,
            url=url,
            config=config,
            login_request=login_request,
            code=code,
            password=password,
            post_id=post_id,
            before_post_id=before_post_id,
            search=search,
            language_id=self.context.config.gui_language,
            parent=self.context.window,
        )
        self.context.lifecycle.workers.begin_telegram(worker)
        worker.videos_ready.connect(
            lambda videos, op=operation: self.context.channel_flow._telegram_items_ready(videos, op)
        )
        worker.login_request_ready.connect(self.context.sources._telegram_login_request_ready)
        worker.login_ready.connect(self.context.sources._telegram_login_ready)
        worker.password_required.connect(self.context.sources._telegram_password_required)
        worker.progress_changed.connect(self.context.source_progress._telegram_download_progress_changed)
        worker.video_ready.connect(self.context.sources._telegram_video_ready)
        worker.failed.connect(lambda message, op=operation: self.context.sources._telegram_worker_failed(op, message))
        worker.finished.connect(lambda worker=worker: self.context.sources._telegram_worker_finished(worker))
        worker.start()

    def _telegram_items_ready(self, items, operation: str = "") -> None:
        continuation = ""
        if hasattr(items, "items"):
            continuation = str(getattr(items, "continuation", "") or "")
            items = getattr(items, "items", [])
        items = list(items)
        if operation in {"list_youtube", "list_youtube_more"}:
            self.context.channel_flow._telegram_channel_provider = "youtube"
            self.context.sources.channel.channel_continuation = continuation
        if operation.endswith("_more"):
            self.context.sources.channel.auto_load_pending_before_post_id = ""
            self.context.sources._append_telegram_channel_items(items)
        else:
            self.context.sources.channel.auto_load_pending_before_post_id = ""
            self.context.sources._set_telegram_channel_items(items)
        if operation in {"list_authenticated", "list_authenticated_more"}:
            self.context.sources.channel.channel_authenticated = True
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_login_ready"))
        elif operation in {"list_youtube", "list_youtube_more"}:
            self.context.sources.channel.channel_authenticated = False
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("youtube_channel_browser_ready").format(
                    count=len(self.context.sources.channel.channel_all_items)
                )
            )
        else:
            self.context.sources.channel.channel_authenticated = False
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("telegram_channel_browser_ready").format(
                    count=len(self.context.sources.channel.channel_all_items)
                )
            )
        pending_direction = int(self.context.get("_pending_telegram_navigation_direction", 0) or 0)
        if pending_direction and operation.endswith("_more"):
            self.context.sources.channel.pending_navigation_direction = 0
            self.context.sources._open_adjacent_telegram_channel_video(pending_direction, allow_load_more=False)
        self.context.sources._maybe_auto_translate_telegram_channel()

    def _telegram_videos_ready(self, videos) -> None:
        self.context.channel_flow._telegram_items_ready(videos)
