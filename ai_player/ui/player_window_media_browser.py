from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QPushButton, QStyle

DEFAULT_MEDIA_HOME_URL = "https://www.google.com"


def build_media_browser_buttons(owner) -> None:
    owner._media_home_button = QPushButton(owner.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "")
    owner._media_home_button.setObjectName("mediaHomeButton")
    owner._media_home_button.setProperty("i18n_tooltip_key", "google_home_tooltip")
    owner._media_home_button.setToolTip(owner._tr("google_home_tooltip"))
    owner._media_home_button.setFixedSize(owner._ICON_BUTTON_SIZE, owner._ICON_BUTTON_SIZE)
    owner._media_home_button.clicked.connect(owner._open_media_home)

    owner._telegram_browser_button = QPushButton(owner.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "")
    owner._telegram_browser_button.setObjectName("telegramBrowserButton")
    owner._telegram_browser_button.setProperty("i18n_key", "telegram_channel_back")
    owner._telegram_browser_button.setProperty("i18n_tooltip_key", "telegram_channel_back")
    owner._telegram_browser_button.setToolTip(owner._tr("telegram_channel_back"))
    owner._telegram_browser_button.setFixedSize(owner._ICON_BUTTON_SIZE, owner._ICON_BUTTON_SIZE)
    owner._telegram_browser_button.clicked.connect(owner._return_to_telegram_channel_browser)
    owner._telegram_browser_button.hide()


class PlayerMediaBrowserMixin:
    def _sync_media_browser_state(self) -> None:
        sync_start = getattr(self, "_sync_media_start_overlay", None)
        if callable(sync_start):
            sync_start()
        self._sync_media_home_button()
        self._sync_media_browser_address()

    def _open_media_home(self) -> None:
        if not hasattr(self, "_video_placeholder"):
            return
        set_url = getattr(self._video_placeholder, "setUrl", None)
        if callable(set_url):
            set_url(QUrl(DEFAULT_MEDIA_HOME_URL))
        if hasattr(self, "_media_stack"):
            self._media_stack.setCurrentWidget(self._video_placeholder)
        self._sync_media_browser_state()

    def _sync_media_home_button(self) -> None:
        button = getattr(self, "_media_home_button", None)
        media_stack = getattr(self, "_media_stack", None)
        placeholder = getattr(self, "_video_placeholder", None)
        if button is None or media_stack is None or placeholder is None:
            return
        start_page = getattr(self, "_media_start_page", None)
        button.setVisible(
            media_stack.currentWidget() in {start_page, placeholder}
            and callable(getattr(placeholder, "setUrl", None))
        )

    def _sync_media_browser_address(self) -> None:
        media_stack = getattr(self, "_media_stack", None)
        placeholder = getattr(self, "_video_placeholder", None)
        source_label = getattr(self, "_source_label", None)
        if media_stack is None or placeholder is None or source_label is None:
            return
        start_page = getattr(self, "_media_start_page", None)
        if start_page is not None and media_stack.currentWidget() is start_page:
            source_label.setText(self._tr("source_empty"))
            return
        if media_stack.currentWidget() is not placeholder:
            return
        url_getter = getattr(placeholder, "url", None)
        if not callable(url_getter):
            source_label.setText(self._tr("source_empty"))
            return
        url = url_getter().toString()
        source_label.setText(url or self._tr("source_empty"))
