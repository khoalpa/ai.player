from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QPushButton, QStyle

from ai_player.ui.features.base import Feature

DEFAULT_MEDIA_HOME_URL = "https://www.google.com"


def build_media_browser_buttons(owner) -> None:
    owner.bindings._media_home_button = QPushButton(
        owner.window.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), ""
    )
    owner.bindings._media_home_button.setObjectName("mediaHomeButton")
    owner.bindings._media_home_button.setProperty("i18n_tooltip_key", "google_home_tooltip")
    owner.bindings._media_home_button.setToolTip(owner.settings._tr("google_home_tooltip"))
    owner.bindings._media_home_button.setFixedSize(owner.ui._ICON_BUTTON_SIZE, owner.ui._ICON_BUTTON_SIZE)
    owner.bindings._media_home_button.clicked.connect(owner.media_browser._open_media_home)

    owner.bindings._telegram_browser_button = QPushButton(
        owner.window.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), ""
    )
    owner.bindings._telegram_browser_button.setObjectName("telegramBrowserButton")
    owner.bindings._telegram_browser_button.setProperty("i18n_key", "telegram_channel_back")
    owner.bindings._telegram_browser_button.setProperty("i18n_tooltip_key", "telegram_channel_back")
    owner.bindings._telegram_browser_button.setToolTip(owner.settings._tr("telegram_channel_back"))
    owner.bindings._telegram_browser_button.setFixedSize(owner.ui._ICON_BUTTON_SIZE, owner.ui._ICON_BUTTON_SIZE)
    owner.bindings._telegram_browser_button.clicked.connect(owner.channel_browser._return_to_telegram_channel_browser)
    owner.bindings._telegram_browser_button.hide()


class PlayerMediaBrowserFeature(Feature):
    def _sync_media_browser_state(self) -> None:
        sync_start = self.context.get("_sync_media_start_overlay", None)
        if callable(sync_start):
            sync_start()
        self.context.media_browser._sync_media_home_button()
        self.context.media_browser._sync_media_browser_address()

    def _open_media_home(self) -> None:
        if not self.context.has("_video_placeholder"):
            return
        set_url = getattr(self.context.layout._video_placeholder, "setUrl", None)
        if callable(set_url):
            set_url(QUrl(DEFAULT_MEDIA_HOME_URL))
        if self.context.has("_media_stack"):
            self.context.layout._media_stack.setCurrentWidget(self.context.layout._video_placeholder)
        self.context.media_browser._sync_media_browser_state()

    def _sync_media_home_button(self) -> None:
        button = self.context.get("_media_home_button", None)
        media_stack = self.context.get("_media_stack", None)
        placeholder = self.context.get("_video_placeholder", None)
        if button is None or media_stack is None or placeholder is None:
            return
        start_page = self.context.get("_media_start_page", None)
        button.setVisible(
            media_stack.currentWidget() in {start_page, placeholder} and callable(getattr(placeholder, "setUrl", None))
        )

    def _sync_media_browser_address(self) -> None:
        media_stack = self.context.get("_media_stack", None)
        placeholder = self.context.get("_video_placeholder", None)
        source_label = self.context.get("_source_label", None)
        if media_stack is None or placeholder is None or source_label is None:
            return
        start_page = self.context.get("_media_start_page", None)
        if start_page is not None and media_stack.currentWidget() is start_page:
            source_label.setText(self.context.settings._tr("source_empty"))
            return
        if media_stack.currentWidget() is not placeholder:
            return
        url_getter = getattr(placeholder, "url", None)
        if not callable(url_getter):
            source_label.setText(self.context.settings._tr("source_empty"))
            return
        url = url_getter().toString()
        source_label.setText(url or self.context.settings._tr("source_empty"))
