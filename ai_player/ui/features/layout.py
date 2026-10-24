from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF
from PySide6.QtCore import QSize as QSize
from PySide6.QtCore import Qt as Qt
from PySide6.QtCore import QUrl as QUrl
from PySide6.QtGui import QAction as QAction
from PySide6.QtGui import QColor as QColor
from PySide6.QtGui import QKeySequence as QKeySequence
from PySide6.QtGui import QPainter, QTextDocument
from PySide6.QtGui import QPalette as QPalette
from PySide6.QtGui import QShortcut as QShortcut
from PySide6.QtMultimediaWidgets import QVideoWidget as QVideoWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
)
from PySide6.QtWidgets import QCheckBox as QCheckBox
from PySide6.QtWidgets import QComboBox as QComboBox
from PySide6.QtWidgets import QFrame as QFrame
from PySide6.QtWidgets import QGridLayout as QGridLayout
from PySide6.QtWidgets import QHBoxLayout as QHBoxLayout
from PySide6.QtWidgets import QLabel as QLabel
from PySide6.QtWidgets import QLineEdit as QLineEdit
from PySide6.QtWidgets import QListWidget as QListWidget
from PySide6.QtWidgets import QMenu as QMenu
from PySide6.QtWidgets import QProgressBar as QProgressBar
from PySide6.QtWidgets import QPushButton as QPushButton
from PySide6.QtWidgets import QScrollArea as QScrollArea
from PySide6.QtWidgets import QSizePolicy as QSizePolicy
from PySide6.QtWidgets import QSlider as QSlider
from PySide6.QtWidgets import QSplitter as QSplitter
from PySide6.QtWidgets import QStackedWidget as QStackedWidget
from PySide6.QtWidgets import QStatusBar as QStatusBar
from PySide6.QtWidgets import QStyle as QStyle
from PySide6.QtWidgets import QTextEdit as QTextEdit
from PySide6.QtWidgets import QVBoxLayout as QVBoxLayout
from PySide6.QtWidgets import QWidget as QWidget

from ai_player.ui.features.base import Feature

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView as QWebEngineView
except ImportError:
    QWebEnginePage = None
    QWebEngineScript = None
    QWebEngineSettings = None
    QWebEngineView = None

from ai_player.adapters.ai.speaker_voice_selector import (
    normalize_speaker_gender_provider as normalize_speaker_gender_provider,
)
from ai_player.adapters.ai.speaker_voice_selector import normalize_voice_gender_mode as normalize_voice_gender_mode
from ai_player.adapters.media.source_voice_filter import (
    SOURCE_VOICE_FILTER_DEMUCS_MODELS as SOURCE_VOICE_FILTER_DEMUCS_MODELS,
)
from ai_player.adapters.media.source_voice_filter import (
    normalize_source_voice_filter_model as normalize_source_voice_filter_model,
)
from ai_player.adapters.sources.video_source import is_supported_browser_video_url
from ai_player.adapters.tts.tts_base import available_vieneu_modes as available_vieneu_modes
from ai_player.runtime.runtime_catalog import available_asr_models as available_asr_models
from ai_player.runtime.runtime_catalog import available_gui_language_options as available_gui_language_options
from ai_player.runtime.runtime_catalog import available_language_options as available_language_options
from ai_player.runtime.runtime_catalog import available_local_llm_options as available_local_llm_options
from ai_player.runtime.runtime_catalog import available_ocr_models as available_ocr_models
from ai_player.runtime.runtime_catalog import available_ocr_providers as available_ocr_providers
from ai_player.runtime.runtime_catalog import available_speaker_gender_models as available_speaker_gender_models
from ai_player.ui.features.media import DEFAULT_SIDEBAR_PANEL_SIZES as DEFAULT_SIDEBAR_PANEL_SIZES
from ai_player.ui.features.media_browser import DEFAULT_MEDIA_HOME_URL as DEFAULT_MEDIA_HOME_URL
from ai_player.ui.features.media_browser import build_media_browser_buttons as build_media_browser_buttons
from ai_player.ui.features.readiness import READINESS_PROFILES
from ai_player.ui.media_start_panel import (
    auto_goal_profile,
    auto_goal_profile_reason_keys,
    preset_card_detail_key,
    recent_source_label,
    workflow_badge_key,
)
from ai_player.ui.player_window_settings_tabs import build_advanced_settings_tab as build_advanced_settings_tab
from ai_player.ui.player_window_settings_tabs import build_basic_settings_tab as build_basic_settings_tab
from ai_player.ui.player_window_settings_tabs import build_models_settings_tab as build_models_settings_tab
from ai_player.ui.player_window_settings_tabs import build_settings_panel as build_settings_panel
from ai_player.ui.player_window_settings_tabs import build_settings_tabs as build_settings_tabs
from ai_player.ui.player_window_settings_tabs import build_transcript_settings_tab as build_transcript_settings_tab
from ai_player.ui.player_window_utils import (
    dropdown_options as _dropdown_options,
)
from ai_player.ui.player_window_utils import (
    ui_label as _ui_label,
)
from ai_player.ui.provider_preview_panel import add_provider_preview_row as add_provider_preview_row
from ai_player.ui.provider_preview_panel import build_provider_preview_panel as build_provider_preview_panel

DEFAULT_MEDIA_ASPECT_RATIO = "16:9"
TELEGRAM_ITEM_HTML_ROLE = Qt.ItemDataRole.UserRole.value + 10
TELEGRAM_BLACKLIST_BUTTON_ROLE = Qt.ItemDataRole.UserRole.value + 11
TELEGRAM_BLACKLIST_BUTTON_WIDTH = 88
TELEGRAM_BLACKLIST_BUTTON_HEIGHT = 30
TELEGRAM_BLACKLIST_BUTTON_MARGIN = 10
TELEGRAM_TRANSLATION_COLOR = "#0f766e"
TELEGRAM_BROWSER_HOSTS = {"t.me", "telegram.me", "web.telegram.org", "telegram.org"}
TELEGRAM_PUBLIC_CHANNEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
TELEGRAM_IN_PLAYER_SCRIPT_NAME = "ai-player-telegram-in-player-links"
TELEGRAM_IN_PLAYER_SCRIPT_SOURCE = r"""
(function() {
  if (window.__aiPlayerTelegramLinksInstalled) {
    return;
  }
  window.__aiPlayerTelegramLinksInstalled = true;

  function firstParam(params, name) {
    var value = params.get(name);
    return value ? value.replace(/^\/+|\/+$/g, '') : '';
  }

  function inPlayerUrl(href) {
    if (!href || href.indexOf('tg://') !== 0) {
      return '';
    }
    var parsed;
    try {
      parsed = new URL(href);
    } catch (e) {
      return '';
    }
    var action = parsed.hostname || parsed.pathname.replace(/^\/+/, '').split('/')[0];
    var params = parsed.searchParams;
    if (action === 'resolve') {
      var domain = firstParam(params, 'domain');
      if (!domain) {
        return 'https://t.me/';
      }
      var post = firstParam(params, 'post');
      return 'https://t.me/' + domain + (post ? '/' + post : '');
    }
    if (action === 'privatepost') {
      var channel = firstParam(params, 'channel').replace(/^-100/, '');
      var privatePost = firstParam(params, 'post');
      if (channel && privatePost) {
        return 'https://t.me/c/' + channel + '/' + privatePost;
      }
    }
    if (action === 'join') {
      var invite = firstParam(params, 'invite');
      if (invite) {
        return 'https://t.me/+' + invite;
      }
    }
    if (action === 'msg_url') {
      return params.get('url') || '';
    }
    return 'https://t.me/';
  }

  function publicChannelName(value) {
    return /^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(value || '');
  }

  function httpTelegramPreviewUrl(href) {
    var parsed;
    try {
      parsed = new URL(href, window.location.href);
    } catch (e) {
      return '';
    }
    var host = parsed.hostname.toLowerCase();
    if (host !== 't.me' && host !== 'telegram.me') {
      return '';
    }
    var parts = parsed.pathname.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean);
    if (parts.length === 1 && publicChannelName(parts[0])) {
      return 'https://t.me/' + parts[0];
    }
    if (parts.length === 2 && publicChannelName(parts[0]) && /^\d+$/.test(parts[1])) {
      return 'https://t.me/' + parts[0] + '/' + parts[1];
    }
    return href;
  }

  function googleResultTelegramTarget(href) {
    var parsed;
    try {
      parsed = new URL(href, window.location.href);
    } catch (e) {
      return '';
    }
    var host = parsed.hostname.toLowerCase();
    if (!(host === 'google.com' || host.endsWith('.google.com')) || parsed.pathname !== '/url') {
      return '';
    }
    return httpTelegramPreviewUrl(parsed.searchParams.get('url') || parsed.searchParams.get('q') || '');
  }

  function linkTarget(href) {
    return inPlayerUrl(href) || googleResultTelegramTarget(href) || httpTelegramPreviewUrl(href);
  }

  function patchLinks() {
    var links = document.querySelectorAll('a[href]');
    for (var index = 0; index < links.length; index += 1) {
      var link = links[index];
      var target = linkTarget(link.getAttribute('href') || link.href || '');
      if (!target) {
        continue;
      }
      link.href = target;
      link.target = '_self';
      link.removeAttribute('rel');
      link.onclick = function(event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        event.stopPropagation();
        window.location.href = this.href;
        return false;
      };
    }
  }

  function handleClick(event) {
    var link = event.target && event.target.closest ? event.target.closest('a') : null;
    var target = link ? linkTarget(link.getAttribute('href') || '') : '';
    if (!target) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    event.stopPropagation();
    window.location.href = target;
  }

  window.addEventListener('click', handleClick, true);
  document.addEventListener('click', handleClick, true);

  var originalOpen = window.open;
  window.open = function(url, name, features) {
    var target = linkTarget(url || '');
    if (target) {
      window.location.href = target;
      return window;
    }
    return originalOpen ? originalOpen.apply(window, arguments) : null;
  };

  patchLinks();
  window.setTimeout(patchLinks, 250);
  window.setTimeout(patchLinks, 1000);
  window.setTimeout(patchLinks, 2500);
})();
"""


def _telegram_in_player_url(value: QUrl | str, *, channel_preview: bool = False) -> QUrl | None:
    url = value.toString() if isinstance(value, QUrl) else str(value or "")
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    google_target = _google_result_telegram_target(parsed, channel_preview=channel_preview)
    if google_target is not None:
        return google_target
    if scheme in {"http", "https"} and host in TELEGRAM_BROWSER_HOSTS:
        if channel_preview:
            preview = _telegram_http_channel_preview_url(parsed)
            if preview is not None:
                return preview
        return QUrl(url)
    if scheme != "tg":
        return None

    action = host or parsed.path.strip("/").split("/", 1)[0].lower()
    query = parse_qs(parsed.query)
    if action == "resolve":
        domain = _first_query_value(query, "domain")
        if not domain:
            return QUrl("https://t.me/")
        post = _first_query_value(query, "post")
        path = f"/{domain.strip('/')}"
        if post:
            path = f"{path}/{post.strip('/')}"
        if channel_preview:
            preview_path = f"/s{path}"
            return QUrl(urlunparse(("https", "t.me", preview_path, "", "", "")))
        passthrough = {
            key: values
            for key, values in query.items()
            if key not in {"domain", "post"} and any(str(value or "").strip() for value in values)
        }
        return QUrl(urlunparse(("https", "t.me", path, "", urlencode(passthrough, doseq=True), "")))
    if action == "privatepost":
        channel = _first_query_value(query, "channel")
        post = _first_query_value(query, "post")
        if channel and post:
            channel = channel.removeprefix("-100").strip("/")
            return QUrl(f"https://t.me/c/{channel}/{post.strip('/')}")
    if action == "join":
        invite = _first_query_value(query, "invite")
        if invite:
            return QUrl(f"https://t.me/+{invite.strip('/')}")
    if action == "msg_url":
        shared_url = _first_query_value(query, "url")
        if shared_url:
            return QUrl(shared_url)
    return QUrl("https://t.me/")


def _player_supported_browser_url(value: QUrl | str) -> QUrl | None:
    telegram_target = _telegram_in_player_url(value, channel_preview=False)
    if telegram_target is not None:
        return telegram_target
    url = value.toString() if isinstance(value, QUrl) else str(value or "")
    parsed = urlparse(url.strip())
    google_target = _google_result_supported_target(parsed)
    if google_target is not None:
        return google_target
    return QUrl(url) if is_supported_browser_video_url(url) else None


def _first_query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0] or "").strip() if values else ""


def _telegram_http_channel_preview_url(parsed) -> QUrl | None:
    host = parsed.netloc.lower()
    if host not in {"t.me", "telegram.me"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) == 1 and _telegram_public_channel_name(parts[0]):
        return QUrl(urlunparse(("https", "t.me", f"/s/{parts[0]}", "", "", "")))
    if len(parts) == 2 and _telegram_public_channel_name(parts[0]) and parts[1].isdigit():
        return QUrl(urlunparse(("https", "t.me", f"/s/{parts[0]}/{parts[1]}", "", "", "")))
    return None


def _google_result_telegram_target(parsed, *, channel_preview: bool = False) -> QUrl | None:
    host = parsed.netloc.lower()
    if not (host == "google.com" or host.endswith(".google.com")):
        return None
    if parsed.path != "/url":
        return None
    query = parse_qs(parsed.query)
    target = _first_query_value(query, "url") or _first_query_value(query, "q")
    if not target:
        return None
    target_url = _telegram_in_player_url(target, channel_preview=channel_preview)
    return target_url if target_url is not None else None


def _google_result_supported_target(parsed) -> QUrl | None:
    host = parsed.netloc.lower()
    if not (host == "google.com" or host.endswith(".google.com")):
        return None
    if parsed.path != "/url":
        return None
    query = parse_qs(parsed.query)
    target = _first_query_value(query, "url") or _first_query_value(query, "q")
    if not target:
        return None
    telegram_target = _telegram_in_player_url(target, channel_preview=False)
    if telegram_target is not None:
        return telegram_target
    return QUrl(target) if is_supported_browser_video_url(target) else None


def _telegram_public_channel_name(value: str) -> bool:
    return bool(TELEGRAM_PUBLIC_CHANNEL_RE.fullmatch(str(value or "")))


if QWebEnginePage is not None:

    class _InPlayerWebEngineView(QWebEngineView):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._install_web_child_event_filters()

        def childEvent(self, event) -> None:  # noqa: N802
            super().childEvent(event)
            if event.type() == QEvent.Type.ChildAdded:
                self._install_web_child_event_filter(event.child())

        def eventFilter(self, watched, event) -> bool:
            if self._handle_web_mouse_event(event):
                return True
            return super().eventFilter(watched, event)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            self._open_supported_link_at(event)
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if self._open_hovered_supported_url():
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def _install_web_child_event_filters(self) -> None:
            for child in self.findChildren(QWidget):
                self._install_web_child_event_filter(child)

        def _install_web_child_event_filter(self, child) -> None:
            if child is None or child is self:
                return
            if child.property("ai_player_web_event_filter"):
                return
            child.setProperty("ai_player_web_event_filter", True)
            child.installEventFilter(self)

        def _handle_web_mouse_event(self, event) -> bool:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._open_supported_link_at(event)
                return False
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                return self._open_hovered_supported_url()
            return False

        def _open_hovered_supported_url(self) -> bool:
            page = self.page()
            open_hovered = getattr(page, "_open_hovered_supported_url", None)
            return bool(callable(open_hovered) and open_hovered())

        def _open_supported_link_at(self, event) -> None:
            point = self._event_view_position(event)
            script = (
                "(() => {"
                f"const el = document.elementFromPoint({point.x()}, {point.y()});"
                "const a = el && el.closest ? el.closest('a') : null;"
                "return a ? (a.href || a.getAttribute('href') || '') : '';"
                "})()"
            )
            self.page().runJavaScript(script, self._open_supported_link_from_js)

        def _open_telegram_link_at(self, event) -> None:
            self._open_supported_link_at(event)

        def _event_view_position(self, event) -> QPoint:
            global_position = getattr(event, "globalPosition", None)
            if callable(global_position):
                return self.mapFromGlobal(global_position().toPoint())
            return event.position().toPoint()

        def _open_supported_link_from_js(self, href) -> None:
            target = _player_supported_browser_url(str(href or ""))
            if target is not None:
                self._open_supported_url_in_player(target)

        def _open_supported_url_in_player(self, url: QUrl) -> None:
            window = self.window()
            open_url = getattr(window, "_open_url_from_browser", None)
            if callable(open_url):
                open_url(url.toString())
                return
            self.setUrl(url)

    class _InPlayerWebEnginePage(QWebEnginePage):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            if QWebEngineSettings is not None:
                self.settings().setUnknownUrlSchemePolicy(
                    QWebEngineSettings.UnknownUrlSchemePolicy.AllowAllUnknownUrlSchemes
                )
                self.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            self._install_telegram_link_script()
            self.urlChanged.connect(self._redirect_telegram_channel_landing)
            self.loadFinished.connect(self._page_load_finished)
            self.newWindowRequested.connect(self._open_new_window_in_player)
            self.linkHovered.connect(self._supported_link_hovered)
            self.fullScreenRequested.connect(self._full_screen_requested)
            self._hovered_supported_url = QUrl()

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # noqa: N802
            link_clicked = navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
            target = _player_supported_browser_url(url)
            scheme = url.scheme().lower()
            if link_clicked and target is not None:
                self._open_url_in_player(target)
                return False
            if scheme == "tg":
                return False
            if target is not None and self._is_telegram_http_url(target):
                self._open_url_in_player(target)
                return False
            if target is not None and target != url:
                self._open_url_in_player(target)
                return False
            if scheme not in {"about", "blob", "data", "file", "http", "https"}:
                return False
            return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

        def createWindow(self, window_type):  # noqa: N802
            page = _InPlayerPopupPage(self)
            if not hasattr(self, "_popup_pages"):
                self._popup_pages = []
            self._popup_pages.append(page)
            page.destroyed.connect(lambda _obj=None, page=page: self._forget_popup_page(page))
            return page

        def _install_telegram_link_script(self) -> None:
            if QWebEngineScript is None:
                return
            script = QWebEngineScript()
            script.setName(TELEGRAM_IN_PLAYER_SCRIPT_NAME)
            script.setSourceCode(TELEGRAM_IN_PLAYER_SCRIPT_SOURCE)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(True)
            self.scripts().insert(script)

        def _page_load_finished(self, _ok: bool) -> None:
            self._redirect_telegram_channel_landing(self.url())
            self.runJavaScript(TELEGRAM_IN_PLAYER_SCRIPT_SOURCE)

        def _supported_link_hovered(self, url: str) -> None:
            target = _player_supported_browser_url(url)
            self._hovered_supported_url = target if target is not None else QUrl()

        def _telegram_link_hovered(self, url: str) -> None:
            self._supported_link_hovered(url)

        def _open_hovered_supported_url(self) -> bool:
            target = getattr(self, "_hovered_supported_url", QUrl())
            if not target.isValid() or not target.toString():
                return False
            self._open_url_in_player(target)
            return True

        def _open_hovered_telegram_url(self) -> bool:
            return self._open_hovered_supported_url()

        def _full_screen_requested(self, request) -> None:
            request.accept()
            view = self._attached_view()
            window = view.window() if view is not None else None
            set_fullscreen = getattr(window, "_set_video_fullscreen", None)
            if callable(set_fullscreen):
                set_fullscreen(bool(request.toggleOn()))

        def _redirect_telegram_channel_landing(self, url: QUrl) -> None:
            target = _telegram_in_player_url(url, channel_preview=False)
            if target is not None and self._is_telegram_http_url(target):
                self._open_url_in_player(target)

        @staticmethod
        def _is_telegram_http_url(url: QUrl) -> bool:
            parsed = urlparse(url.toString())
            return parsed.scheme.lower() in {"http", "https"} and parsed.netloc.lower() in {"t.me", "telegram.me"}

        def _open_new_window_in_player(self, request) -> None:
            target = _player_supported_browser_url(request.requestedUrl())
            if target is None:
                return
            self._open_url_in_player(target)

        def _open_popup_url(self, url: QUrl) -> None:
            if not url.isValid() or url.toString() in {"", "about:blank"}:
                return
            target = _player_supported_browser_url(url)
            if target is not None:
                self._open_url_in_player(target)
                return
            self._set_player_url(url)

        def _forget_popup_page(self, page) -> None:
            pages = getattr(self, "_popup_pages", None)
            if pages is not None and page in pages:
                pages.remove(page)

        def _set_player_url(self, url: QUrl) -> None:
            view = self._attached_view()
            if view is not None:
                view.setUrl(url)
                return
            self.setUrl(url)

        def _open_url_in_player(self, url: QUrl) -> None:
            view = self._attached_view()
            window = view.window() if view is not None else None
            open_url = getattr(window, "_open_url_from_browser", None)
            if callable(open_url):
                open_url(url.toString())
                return
            self._set_player_url(url)

        def _attached_view(self):
            page_view = getattr(self, "view", None)
            if callable(page_view):
                return page_view()
            parent = self.parent()
            return parent if QWebEngineView is not None and isinstance(parent, QWebEngineView) else None

    class _InPlayerPopupPage(QWebEnginePage):
        def __init__(self, owner: _InPlayerWebEnginePage) -> None:
            super().__init__(owner)
            self._owner = owner
            self.urlChanged.connect(self._url_changed)

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # noqa: N802
            if not url.isValid() or url.toString() in {"", "about:blank"}:
                return True
            self._owner._open_popup_url(url)
            self.deleteLater()
            return False

        def _url_changed(self, url: QUrl) -> None:
            if not url.isValid() or url.toString() in {"", "about:blank"}:
                return
            self._owner._open_popup_url(url)
            self.deleteLater()

else:
    _InPlayerWebEnginePage = None
    _InPlayerWebEngineView = None


class SubtitleOverlayLabel(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subtitle_background_color = QColor(0, 0, 0, 0)

    def setSubtitleBackgroundColor(self, value: str) -> None:
        self._subtitle_background_color = _subtitle_qcolor(value)
        self.update()

    def subtitleBackgroundColor(self) -> QColor:
        return QColor(self._subtitle_background_color)

    def paintEvent(self, event) -> None:
        if self._subtitle_background_color.alpha() > 0:
            painter = QPainter(self)
            painter.fillRect(self.rect(), self._subtitle_background_color)
            painter.end()
        super().paintEvent(event)


class TelegramChannelItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        html = str(index.data(TELEGRAM_ITEM_HTML_ROLE) or "")
        button_label = str(index.data(TELEGRAM_BLACKLIST_BUTTON_ROLE) or "")
        if not html and not button_label:
            super().paint(painter, option, index)
            return

        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        style = item_option.widget.style() if item_option.widget is not None else None
        if style is None:
            super().paint(painter, option, index)
            return

        item_option.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, item_option, painter, item_option.widget)
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText,
            item_option,
            item_option.widget,
        )
        if button_label:
            text_rect.setRight(text_rect.right() - TELEGRAM_BLACKLIST_BUTTON_WIDTH - TELEGRAM_BLACKLIST_BUTTON_MARGIN)
        if html:
            document = QTextDocument()
            document.setDefaultFont(item_option.font)
            document.setHtml(html)
            document.setTextWidth(text_rect.width())

            painter.save()
            painter.translate(text_rect.topLeft())
            document.drawContents(painter, QRectF(0, 0, text_rect.width(), text_rect.height()))
            painter.restore()
        if button_label:
            button_option = QStyleOptionButton()
            button_option.rect = _telegram_blacklist_button_rect(option.rect)
            button_option.text = button_label
            button_option.state = QStyle.StateFlag.State_Enabled
            style.drawControl(QStyle.ControlElement.CE_PushButton, button_option, painter, item_option.widget)


def _telegram_blacklist_button_rect(row_rect: QRect) -> QRect:
    x = row_rect.right() - TELEGRAM_BLACKLIST_BUTTON_WIDTH - TELEGRAM_BLACKLIST_BUTTON_MARGIN
    y = row_rect.top() + TELEGRAM_BLACKLIST_BUTTON_MARGIN
    return QRect(x, y, TELEGRAM_BLACKLIST_BUTTON_WIDTH, TELEGRAM_BLACKLIST_BUTTON_HEIGHT)


def _subtitle_qcolor(value: str) -> QColor:
    text = str(value or "").strip()
    if text.lower().startswith("rgba(") and text.endswith(")"):
        parts = [part.strip() for part in text[5:-1].split(",")]
        if len(parts) == 4:
            try:
                red, green, blue, alpha = [max(0, min(255, int(float(part)))) for part in parts]
                return QColor(red, green, blue, alpha)
            except (OverflowError, ValueError):
                pass
    color = QColor(text)
    return color if color.isValid() else QColor(0, 0, 0, 0)


class PlayerLayoutFeature(Feature):
    def _build_ui(self) -> None:
        from ai_player.ui.views.source_toolbar import build as build_source_toolbar

        build_source_toolbar(self.context)
        from ai_player.ui.views.media_surface import build as build_media_surface

        source_bar, telegram_layout, telegram_tools = build_media_surface(self.context)
        from ai_player.ui.views.channel_panel import build as build_channel_panel

        build_channel_panel(self.context, telegram_layout, telegram_tools)
        from ai_player.ui.views.processing_controls import build as build_processing_controls

        video_panel = build_processing_controls(self.context)
        from ai_player.ui.views.voice_controls import build as build_voice_controls

        build_voice_controls(self.context)
        from ai_player.ui.views.recognition_controls import build as build_recognition_controls

        build_recognition_controls(self.context)
        from ai_player.ui.views.ocr_controls import build as build_ocr_controls

        build_ocr_controls(self.context)
        from ai_player.ui.views.settings_sections import build as build_settings_sections

        sections = build_settings_sections(self.context)
        from ai_player.ui.views.assemble import build as build_assemble

        build_assemble(self.context, source_bar, video_panel, sections)

    def _toggle_display_options(self, visible: bool) -> None:
        if self.context.has("_display_options_panel"):
            self.context.layout._display_options_panel.setVisible(bool(visible))

    def _toggle_task_drawer(self) -> None:
        drawer = self.context.get("_task_drawer", None)
        if drawer is None:
            self.context.readiness._select_settings_tab_for_widget(self.context.task_center._task_center_tab_widget)
            return
        self.context.layout._task_drawer_user_open = not drawer.isVisible()
        drawer.setVisible(self.context.layout._task_drawer_user_open)
        if drawer.isVisible() and self.context.has("_refresh_task_center"):
            self.context.task_center._refresh_task_center()

    def _task_drawer_panel(self) -> QFrame:
        drawer = QFrame()
        drawer.setObjectName("taskDrawer")
        drawer.hide()
        layout = QHBoxLayout(drawer)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.context.layout._task_drawer_state = QLabel(self.context.settings._tr("task_drawer_state_idle"))
        self.context.layout._task_drawer_state.setObjectName("taskDrawerState")
        self.context.layout._task_drawer_state.setProperty("i18n_key", "task_drawer_state_idle")
        self.context.layout._task_drawer_state.setMinimumWidth(88)
        layout.addWidget(self.context.layout._task_drawer_state)
        self.context.layout._task_drawer_summary = QLabel(self.context.settings._tr("task_drawer_idle"))
        self.context.layout._task_drawer_summary.setObjectName("taskDrawerSummary")
        self.context.layout._task_drawer_summary.setProperty("i18n_key", "task_drawer_idle")
        self.context.layout._task_drawer_summary.setWordWrap(True)
        self.context.layout._task_drawer_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.context.layout._task_drawer_summary, 1)
        self.context.layout._task_drawer_stop_button = self.context.ui._make_button(
            "task_center_stop_all",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self.context.layout._task_drawer_stop_button.clicked.connect(self.context.task_center._stop_task_center_tasks)
        self.context.layout._task_drawer_retry_button = self.context.ui._make_button(
            "task_center_retry",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self.context.layout._task_drawer_retry_button.clicked.connect(
            self.context.task_center._retry_task_center_action
        )
        self.context.layout._task_drawer_open_button = self.context.ui._make_button(
            "task_drawer_open_center",
            self.context.window.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self.context.layout._task_drawer_open_button.clicked.connect(self.context.layout._open_task_center_from_drawer)
        layout.addWidget(self.context.layout._task_drawer_stop_button)
        layout.addWidget(self.context.layout._task_drawer_retry_button)
        layout.addWidget(self.context.layout._task_drawer_open_button)
        return drawer

    def _open_task_center_from_drawer(self) -> None:
        if self.context.has("_task_drawer"):
            self.context.layout._task_drawer.hide()
        self.context.layout._task_drawer_user_open = False
        self.context.readiness._select_settings_tab_for_widget(self.context.task_center._task_center_tab_widget)

    def _show_command_palette(self) -> None:
        dialog = QDialog(self.context.window)
        dialog.setWindowTitle(self.context.settings._tr("command_palette_title"))
        layout = QVBoxLayout(dialog)
        prompt = QLabel(self.context.settings._tr("command_palette_prompt"), dialog)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        actions = QListWidget(dialog)
        for key, action_id in (
            ("open_video", "open_video"),
            ("open_url", "open_url"),
            ("open_document", "open_document"),
            ("start_dubbing", "dubbing"),
            ("meeting_start_label", "meeting"),
            ("export_workflow_title", "export"),
            ("task_center_tab", "tasks"),
            ("models_tab", "models"),
            ("runtime_tab", "runtime"),
        ):
            item = QListWidgetItem(self.context.settings._tr(key))
            item.setData(Qt.ItemDataRole.UserRole, action_id)
            actions.addItem(item)
        actions.setCurrentRow(0)
        actions.itemDoubleClicked.connect(lambda *_args: dialog.accept())
        layout.addWidget(actions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        item = actions.currentItem()
        action_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        self.context.layout._run_command_palette_action(str(action_id or ""))

    def _run_command_palette_action(self, action_id: str) -> None:
        if action_id == "open_video":
            self.context.layout._start_workflow("video", self.context.sources._open_video)
        elif action_id == "open_url":
            self.context.layout._start_workflow("url", self.context.sources._open_video_url)
        elif action_id == "open_document":
            self.context.layout._start_workflow("document", self.context.sources._open_document)
        elif action_id == "dubbing":
            self.context.layout._start_workflow("dubbing", self.context.dubbing._start_dubbing_from_header)
        elif action_id == "meeting":
            self.context.layout._start_workflow("meeting", self.context.meeting._toggle_meeting)
        elif action_id == "export":
            self.context.layout._start_workflow("export", self.context.export._show_export_workflow)
        elif action_id == "tasks":
            self.context.readiness._select_settings_tab_for_widget(self.context.task_center._task_center_tab_widget)
        elif action_id == "models":
            self.context.readiness._select_settings_tab_for_widget(self.context.bindings._models_tab_widget)
        elif action_id == "runtime":
            self.context.readiness._select_settings_tab_for_widget(self.context.runtime._runtime_tab_widget)

    def _start_goal_workflow(self, workflow: str, action) -> None:
        selected_profile = str(self.context.get("_readiness_selected_profile", "auto") or "auto")
        profile_key = (
            self.context.layout._auto_goal_profile(str(workflow or "").strip().lower())
            if selected_profile == "auto"
            else selected_profile
        )
        if selected_profile == "auto" and profile_key:
            self.context.task_center._record_task_center_event(
                self.context.settings._tr("first_run_profile_auto"),
                self.context.layout._auto_goal_profile_reason(str(workflow or "").strip().lower(), profile_key),
            )
        if profile_key and self.context.has("_readiness_select_profile"):
            self.context.readiness._readiness_select_profile(profile_key)
            if self.context.has("_apply_readiness_profile"):
                self.context.readiness._apply_readiness_profile()
        self.context.layout._start_workflow(workflow, action)

    def _auto_goal_profile(self, workflow: str) -> str:
        return auto_goal_profile(workflow, offline_ready=self.context.layout._offline_goal_ready())

    def _auto_goal_profile_reason(self, workflow: str, profile_key: str) -> str:
        profile_title_key, reason_key = auto_goal_profile_reason_keys(workflow, profile_key)
        return self.context.settings._tr("auto_preset_selected").format(
            profile=self.context.settings._tr(profile_title_key),
            reason=self.context.settings._tr(reason_key),
        )

    def _offline_goal_ready(self) -> bool:
        config = self.context.get("_config", None)
        if config is None:
            return False
        local_paths = (
            getattr(config, "whisper_model", ""),
            getattr(config, "local_translation_model", ""),
            getattr(config, "vieneu_tts_model_name", ""),
        )
        return (
            bool(getattr(config, "whisper_offline", False))
            and bool(getattr(config, "local_translation_offline", False))
            and bool(getattr(config, "vieneu_tts_offline", False))
            and all(Path(str(path)).exists() for path in local_paths if str(path or "").strip())
        )

    def _refresh_header_menu_text(self) -> None:
        action_texts = (
            ("_open_video_action", "open_video"),
            ("_open_smart_action", "smart_open_files"),
            ("_open_clipboard_source_action", "smart_open_clipboard"),
            ("_open_paste_source_action", "smart_open_paste"),
            ("_open_url_action", "open_url"),
            ("_open_document_action", "open_document"),
            ("_simple_sidebar_action", "simple_sidebar_mode"),
            ("_task_center_action", "task_center_tab"),
            ("_offline_models_action", "offline_models_tab"),
            ("_advanced_settings_action", "advanced_tab"),
            ("_runtime_details_action", "runtime_tab"),
            ("_workflow_health_action", "workflow_health_title"),
            ("_adult_health_action", "adult_health_title"),
            ("_adult_hosts_action", "adult_hosts_title"),
            ("_cache_inspector_action", "cache_inspector_title"),
            ("_clear_workflow_cache_action", "task_center_clear_cache"),
            ("_fullscreen_action", "fullscreen"),
            ("_focus_media_action", "focus_media"),
            ("_toggle_sidebar_action", "panel_hide"),
            ("_sidebar_wider_action", "sidebar_wider"),
            ("_sidebar_narrower_action", "sidebar_narrower"),
            ("_reset_layout_action", "reset"),
            ("_help_action", "help"),
        )
        for action_name, key in action_texts:
            action = self.context.get(action_name, None)
            if action is not None:
                if action_name == "_workflow_health_action":
                    action.setText(self.context.task_center._workflow_health_action_label())
                else:
                    action.setText(self.context.settings._tr(key))

    def _start_workflow(self, workflow: str, action) -> None:
        self.context.layout._apply_workflow_sidebar_context(workflow)
        if callable(action):
            action()
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()

    def _apply_workflow_sidebar_context(self, workflow: str) -> None:
        tabs = self.context.get("_settings_tabs", None)
        if tabs is None:
            return
        workflow_key = str(workflow or "").strip().lower()
        if self.context.get("_simple_sidebar_enabled", True):
            contexts = {
                "video": ({2, 6, 3}, 2),
                "url": ({2, 6, 3}, 2),
                "document": ({2, 6, 3}, 2),
                "dubbing": ({2, 6, 3}, 2),
                "meeting": ({2, 6, 3}, 2),
                "export": ({2, 6, 3}, 2),
            }
        else:
            contexts = {
                "video": ({2, 3, 5, 6, 1}, 2),
                "url": ({2, 3, 5, 6, 1}, 2),
                "document": ({2, 6, 3, 5, 1}, 2),
                "dubbing": ({2, 3, 5, 6, 1}, 2),
                "meeting": ({2, 1, 6, 7}, 2),
                "export": ({2, 5, 6, 1}, 2),
            }
        visible_indexes, current_index = contexts.get(workflow_key, (set(range(tabs.count())), tabs.currentIndex()))
        self.context.layout._set_sidebar_tab_visibility(visible_indexes)
        if self.context.has("_settings_scroll") and self.context.layout._settings_scroll.isHidden():
            self.context.media._set_sidebar_panel_visible(True)
        if 0 <= current_index < tabs.count():
            tabs.setCurrentIndex(current_index)
        self.context.layout._current_workflow_context = workflow_key
        title_key = {
            "video": "first_run_workflow_video",
            "url": "first_run_workflow_url",
            "document": "first_run_workflow_document",
            "dubbing": "start_dubbing",
            "meeting": "first_run_workflow_meeting",
            "export": "export_workflow_title",
        }.get(workflow_key, "settings_group_workflow")
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_workflow_context").format(workflow=self.context.settings._tr(title_key))
        )

    def _set_simple_sidebar_mode(self, enabled: bool) -> None:
        self.context.layout._simple_sidebar_enabled = bool(enabled)
        action = self.context.get("_simple_sidebar_action", None)
        if action is not None and action.isChecked() != self.context.layout._simple_sidebar_enabled:
            action.setChecked(self.context.layout._simple_sidebar_enabled)
        tab_bar = getattr(self.context.layout._settings_tabs, "tabBar", lambda: None)()
        if tab_bar is not None:
            tab_bar.setVisible(not self.context.layout._simple_sidebar_enabled)
        workflow = str(self.context.get("_current_workflow_context", "") or "")
        if workflow:
            self.context.layout._apply_workflow_sidebar_context(workflow)
            return
        visible = (
            {2, 3, 6}
            if self.context.layout._simple_sidebar_enabled
            else set(range(self.context.layout._settings_tabs.count()))
        )
        self.context.layout._set_sidebar_tab_visibility(visible)
        if self.context.layout._settings_tabs.currentIndex() not in visible:
            self.context.layout._settings_tabs.setCurrentIndex(2 if 2 in visible else 0)

    def _set_sidebar_tab_visibility(self, visible_indexes: set[int]) -> None:
        tabs = self.context.get("_settings_tabs", None)
        if tabs is None:
            return
        set_visible = getattr(tabs, "setTabVisible", None)
        if callable(set_visible):
            for index in range(tabs.count()):
                set_visible(index, index in visible_indexes)
        self.context.layout._sync_simple_sidebar_nav()

    def _sync_simple_sidebar_nav(self) -> None:
        buttons = self.context.get("_settings_group_buttons", {})
        if not buttons:
            return
        simple = self.context.get("_simple_sidebar_enabled", True)
        for key, button in buttons.items():
            if button is None:
                continue
            simple_groups = {
                "settings_group_workflow",
                "settings_group_transcript",
                "settings_group_models",
            }
            button.setVisible(not simple or key in simple_groups)

    def _sync_open_source_menu_enabled(self) -> None:
        pairs = (
            ("_open_file_button", "_open_video_action"),
            ("_open_url_button", "_open_url_action"),
            ("_open_document_button", "_open_document_action"),
        )
        any_enabled = False
        for button_name, action_name in pairs:
            button = self.context.get(button_name, None)
            action = self.context.get(action_name, None)
            enabled = bool(button is None or button.isEnabled())
            any_enabled = any_enabled or enabled
            if action is not None:
                action.setEnabled(enabled)
        source_button = self.context.get("_open_source_button", None)
        if source_button is not None:
            source_button.setEnabled(any_enabled)

    def _refresh_open_source_menu(self) -> None:
        action = self.context.get("_open_clipboard_source_action", None)
        if action is None:
            return
        text = self.context.sources._smart_source_clipboard_text()
        supported = self.context.sources._smart_source_text_supported(text)
        action.setVisible(supported)
        action.setEnabled(supported)
        if supported:
            label = self.context.settings._tr("smart_open_clipboard")
            display = text if len(text) <= 48 else f"{text[:45]}..."
            action.setText(f"{label}: {display}")

    def _preset_cards_panel_widget(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("presetCardsPanel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        group = QButtonGroup(panel)
        group.setExclusive(True)
        self.context.layout._preset_card_group = group
        presets = ("low_latency", "offline_lite", "balanced", "quality")
        for index, preset_id in enumerate(presets):
            button = QPushButton()
            button.setObjectName("presetCardButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(70)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setProperty("preset_id", preset_id)
            button.clicked.connect(
                lambda _checked=False, value=preset_id: self.context.layout._select_preset_card(value)
            )
            group.addButton(button)
            self.context.layout._preset_cards[preset_id] = button
            layout.addWidget(button, index // 2, index % 2)
        self.context.layout._refresh_preset_cards()
        return panel

    def _select_preset_card(self, preset_id: str) -> None:
        combo = self.context.get("_performance_preset_combo", None)
        if combo is None:
            return
        self.context.settings._set_combo_data(combo, preset_id)
        self.context.settings._apply_selected_performance_preset()

    def _refresh_preset_cards(self) -> None:
        cards = self.context.get("_preset_cards", {})
        if not cards:
            return
        current = ""
        combo = self.context.get("_performance_preset_combo", None)
        if combo is not None:
            current = str(combo.currentData() or "")
        for preset_id, button in cards.items():
            label = self.context.layout._preset_display_label(preset_id)
            detail = self.context.layout._preset_card_detail(preset_id)
            button.setText(f"{label}\n{detail}" if detail else label)
            button.setChecked(preset_id == current)
            button.setToolTip(detail or label)

    def _preset_card_detail(self, preset_id: str) -> str:
        return self.context.settings._tr(preset_card_detail_key(preset_id))

    def _media_start_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("mediaStartPanel")
        panel.setMaximumWidth(16777215)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        grid_host = QWidget()
        grid_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.context.layout._media_start_workflow_buttons = {}
        self.context.layout._media_start_workflow_cards = {}
        for index, (workflow_key, title_key, detail_key, icon_name, preset_id, callback) in enumerate(
            (
                (
                    "video",
                    "first_run_workflow_video",
                    "first_run_workflow_video_detail",
                    "video",
                    "low_latency",
                    self.context.sources._open_video,
                ),
                (
                    "url",
                    "first_run_workflow_url",
                    "first_run_workflow_url_detail",
                    "url",
                    "online_lite",
                    self.context.sources._open_video_url,
                ),
                (
                    "document",
                    "first_run_workflow_document",
                    "first_run_workflow_document_detail",
                    "document",
                    "offline_lite",
                    self.context.sources._open_document,
                ),
                (
                    "meeting",
                    "first_run_workflow_meeting",
                    "first_run_workflow_meeting_detail",
                    "meeting",
                    "low_latency",
                    self.context.meeting._toggle_meeting,
                ),
            )
        ):
            card = self.context.layout._media_start_workflow_card(
                workflow_key=workflow_key,
                title_key=title_key,
                detail_key=detail_key,
                icon_name=icon_name,
                preset_id=preset_id,
                callback=callback,
            )
            grid.addWidget(card, index // 2, index % 2)
            self.context.layout._media_start_workflow_cards[workflow_key] = card
            self.context.layout._media_start_workflow_buttons[title_key] = card._workflow_compat_button
        layout.addWidget(grid_host)

        layout.addWidget(self.context.layout._media_start_quick_panel())

        setup_title = QPushButton(self.context.settings._tr("first_run_profile_change"))
        setup_title.setObjectName("mediaStartSetupTitle")
        setup_title.setProperty("i18n_key", "first_run_profile_change")
        setup_title.setCheckable(True)
        setup_title.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
        setup_title.setFixedWidth(self.context.ui._COMMAND_BUTTON_WIDTH)
        layout.addWidget(setup_title)

        profile_row = QWidget()
        self.context.layout._media_start_profile_row = profile_row
        profile_layout = QHBoxLayout(profile_row)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(8)
        self.context.layout._media_start_profile_group = QButtonGroup(profile_row)
        self.context.layout._media_start_profile_group.setExclusive(True)
        self.context.layout._media_start_profile_buttons = {}
        for profile in READINESS_PROFILES:
            profile_key = profile.key
            button = QPushButton(self.context.settings._tr(profile.title_key))
            button.setObjectName("mediaStartProfileButton")
            button.setCheckable(True)
            button.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
            button.setFixedWidth(self.context.ui._COMMAND_BUTTON_WIDTH)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("launcher_profile", profile_key)
            button.setProperty("launcher_profile_title_key", profile.title_key)
            button.setProperty("launcher_profile_detail_key", profile.detail_key)
            button.clicked.connect(
                lambda _checked=False, key=profile_key: self.context.layout._apply_media_start_profile(key)
            )
            self.context.layout._media_start_profile_group.addButton(button)
            self.context.layout._media_start_profile_buttons[profile_key] = button
            profile_layout.addWidget(button)
        profile_row.setVisible(False)
        setup_title.toggled.connect(profile_row.setVisible)
        layout.addWidget(profile_row)
        self.context.layout._refresh_media_start_launcher_text()
        return panel

    def _media_start_quick_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("mediaStartQuickPanel")
        panel.setAcceptDrops(True)
        panel.installEventFilter(self.context.window)
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)

        drop_zone = QFrame()
        drop_zone.setObjectName("mediaStartDropZone")
        drop_zone.setAcceptDrops(True)
        drop_zone.installEventFilter(self.context.window)
        drop_layout = QVBoxLayout(drop_zone)
        drop_layout.setContentsMargins(12, 10, 12, 10)
        drop_layout.setSpacing(6)
        drop_title = QLabel(self.context.settings._tr("media_start_drop_title"))
        drop_title.setObjectName("mediaStartDropTitle")
        drop_title.setProperty("i18n_key", "media_start_drop_title")
        drop_detail = QLabel(self.context.settings._tr("media_start_drop_detail"))
        drop_detail.setObjectName("mediaStartDropDetail")
        drop_detail.setProperty("i18n_key", "media_start_drop_detail")
        drop_detail.setWordWrap(True)
        drop_layout.addWidget(drop_title)
        drop_layout.addWidget(drop_detail)

        quick_row = QWidget()
        quick_layout = QHBoxLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setSpacing(6)
        quick_edit = QLineEdit()
        quick_edit.setObjectName("mediaStartQuickSourceEdit")
        quick_edit.setProperty("i18n_key", "media_start_quick_placeholder")
        quick_edit.setPlaceholderText(self.context.settings._tr("media_start_quick_placeholder"))
        quick_edit.setClearButtonEnabled(True)
        quick_edit.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
        quick_edit.returnPressed.connect(self.context.sources._media_start_submit_quick_source)
        quick_button = QPushButton(
            self.context.ui._app_icon("open"), self.context.settings._tr("media_start_quick_open")
        )
        quick_button.setObjectName("mediaStartQuickOpenButton")
        quick_button.setProperty("i18n_key", "media_start_quick_open")
        quick_button.setCursor(Qt.PointingHandCursor)
        quick_button.setFixedSize(self.context.ui._COMMAND_BUTTON_WIDTH, self.context.ui._COMMAND_BUTTON_HEIGHT)
        quick_button.clicked.connect(self.context.sources._media_start_submit_quick_source)
        quick_layout.addWidget(quick_edit, 1)
        quick_layout.addWidget(quick_button)
        drop_layout.addWidget(quick_row)

        info_panel = QFrame()
        info_panel.setObjectName("mediaStartInfoPanel")
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(7)
        recent_title = QLabel(self.context.settings._tr("media_start_recent_title"))
        recent_title.setObjectName("mediaStartSectionTitle")
        recent_title.setProperty("i18n_key", "media_start_recent_title")
        info_layout.addWidget(recent_title)
        self.context.layout._media_start_recent_empty_label = QLabel(
            self.context.settings._tr("media_start_recent_empty")
        )
        self.context.layout._media_start_recent_empty_label.setObjectName("mediaStartMutedText")
        self.context.layout._media_start_recent_empty_label.setProperty("i18n_key", "media_start_recent_empty")
        self.context.layout._media_start_recent_empty_label.setWordWrap(True)
        info_layout.addWidget(self.context.layout._media_start_recent_empty_label)
        self.context.layout._media_start_recent_buttons = []
        for _index in range(3):
            button = QPushButton()
            button.setObjectName("mediaStartRecentButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(30)
            button.clicked.connect(
                lambda _checked=False, source_button=button: self.context.sources._open_media_start_recent_source(
                    str(source_button.property("source") or "")
                )
            )
            button.hide()
            self.context.layout._media_start_recent_buttons.append(button)
            info_layout.addWidget(button)

        config_title = QLabel(self.context.settings._tr("media_start_config_title"))
        config_title.setObjectName("mediaStartSectionTitle")
        config_title.setProperty("i18n_key", "media_start_config_title")
        info_layout.addWidget(config_title)
        self.context.layout._media_start_config_summary = QLabel()
        self.context.layout._media_start_config_summary.setObjectName("mediaStartConfigSummary")
        self.context.layout._media_start_config_summary.setWordWrap(True)
        info_layout.addWidget(self.context.layout._media_start_config_summary)

        self.context.layout._media_start_drop_zone = drop_zone
        self.context.layout._media_start_quick_source_edit = quick_edit
        self.context.layout._media_start_quick_open_button = quick_button
        layout.addWidget(drop_zone, 0, 0)
        layout.addWidget(info_panel, 0, 1)
        self.context.layout._refresh_media_start_context()
        return panel

    def _media_start_workflow_card(
        self,
        *,
        workflow_key: str,
        title_key: str,
        detail_key: str,
        icon_name: str,
        preset_id: str,
        callback,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("mediaStartWorkflowCard")
        card.setProperty("workflow_key", workflow_key)
        card.setProperty("workflow_title_key", title_key)
        card.setProperty("workflow_detail_key", detail_key)
        card.setProperty("workflow_preset_id", preset_id)
        card.setMinimumHeight(108)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        body = QWidget(card)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        icon = QLabel()
        icon.setObjectName("mediaStartWorkflowIcon")
        icon.setPixmap(self.context.ui._app_icon(icon_name).pixmap(22, 22))
        header_layout.addWidget(icon)
        title = QLabel(self.context.settings._tr(title_key))
        title.setObjectName("mediaStartWorkflowTitle")
        title.setProperty("i18n_key", title_key)
        title.setWordWrap(True)
        header_layout.addWidget(title, 1)
        body_layout.addWidget(header)

        detail = QLabel(self.context.settings._tr(detail_key))
        detail.setObjectName("mediaStartWorkflowDetail")
        detail.setProperty("i18n_key", detail_key)
        detail.setWordWrap(True)
        body_layout.addWidget(detail)

        runtime = QLabel(self.context.layout._workflow_runtime_status_text(workflow_key, preset_id))
        runtime.setObjectName("mediaStartWorkflowRuntime")
        runtime.setWordWrap(False)
        runtime.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        body_layout.addWidget(runtime, 0, Qt.AlignmentFlag.AlignLeft)
        body_layout.addStretch(1)
        layout.addWidget(body, 1)

        actions = QWidget()
        actions.setObjectName("workflowCardActions")
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        actions_layout.addStretch(1)
        open_button = QPushButton(self.context.ui._app_icon("open"), self.context.settings._tr("workflow_card_open"))
        open_button.setObjectName("workflowCardPrimaryButton")
        open_button.setProperty("i18n_key", "workflow_card_open")
        open_button.setCursor(Qt.PointingHandCursor)
        open_button.setFixedHeight(self.context.ui._COMMAND_BUTTON_HEIGHT)
        open_button.setFixedWidth(self.context.ui._COMMAND_BUTTON_WIDTH)
        open_button.clicked.connect(
            lambda _checked=False, key=workflow_key, cb=callback: self.context.layout._start_goal_workflow(key, cb)
        )
        compat_button = QPushButton(self.context.settings._tr(title_key), card)
        compat_button.setObjectName("mediaStartWorkflowButton")
        compat_button.setProperty("i18n_key", title_key)
        compat_button.setToolTip(self.context.layout._media_start_button_tooltip(title_key, detail_key))
        compat_button.clicked.connect(
            lambda _checked=False, key=workflow_key, cb=callback: self.context.layout._start_goal_workflow(key, cb)
        )
        compat_button.hide()
        preset_button = QPushButton(self.context.settings._tr("workflow_card_quick_preset"))
        preset_button.setObjectName("workflowCardSecondaryButton")
        preset_button.setProperty("i18n_key", "workflow_card_quick_preset")
        preset_button.setCursor(Qt.PointingHandCursor)
        preset_button.setToolTip(self.context.layout._workflow_preset_tooltip(workflow_key, preset_id))
        preset_button.setFixedSize(self.context.ui._COMMAND_BUTTON_WIDTH, self.context.ui._COMMAND_BUTTON_HEIGHT)
        preset_button.clicked.connect(
            lambda _checked=False, key=workflow_key, preset=preset_id: self.context.layout._apply_workflow_quick_preset(
                key, preset
            )
        )
        actions_layout.addWidget(open_button)
        actions_layout.addWidget(preset_button)
        actions_layout.addStretch(1)
        layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignRight)

        card._workflow_title = title
        card._workflow_detail = detail
        card._workflow_runtime = runtime
        card._workflow_open_button = open_button
        card._workflow_compat_button = compat_button
        card._workflow_preset_button = preset_button
        return card

    def _workflow_runtime_status_text(self, workflow_key: str, preset_id: str) -> str:
        preset_label = self.context.layout._preset_display_label(preset_id)
        requirements = workflow_badge_key(workflow_key)
        return self.context.settings._tr(requirements).format(preset=preset_label)

    def _workflow_preset_tooltip(self, workflow_key: str, preset_id: str) -> str:
        return self.context.settings._tr("workflow_preset_tooltip").format(
            workflow=self.context.settings._tr(f"workflow_name_{workflow_key}"),
            preset=self.context.layout._preset_display_label(preset_id),
        )

    def _preset_display_label(self, preset_id: str) -> str:
        combo = self.context.get("_performance_preset_combo", None)
        if combo is not None:
            index = combo.findData(preset_id)
            if index >= 0:
                return combo.itemText(index)
        for label, value in _dropdown_options("performance_presets", self.context.settings._ui_language()):
            if value == preset_id:
                return _ui_label(label)
        return str(preset_id or "")

    def _apply_workflow_quick_preset(self, workflow_key: str, preset_id: str) -> None:
        combo = self.context.get("_performance_preset_combo", None)
        if combo is not None:
            self.context.settings._set_combo_data(combo, preset_id)
            self.context.settings._apply_selected_performance_preset()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("workflow_quick_preset_applied").format(
                workflow=self.context.settings._tr(f"workflow_name_{workflow_key}"),
                preset=self.context.layout._preset_display_label(preset_id),
            )
        )

    def _apply_media_start_profile(self, profile_key: str) -> None:
        if self.context.has("_readiness_select_profile"):
            self.context.readiness._readiness_select_profile(profile_key)
        else:
            self.context.readiness._readiness_selected_profile = profile_key
        if self.context.has("_apply_readiness_profile"):
            self.context.readiness._apply_readiness_profile()
        self.context.layout._sync_media_start_profile_buttons()

    def _refresh_media_start_launcher_text(self) -> None:
        for card in self.context.get("_media_start_workflow_cards", {}).values():
            title_key = str(card.property("workflow_title_key") or "")
            detail_key = str(card.property("workflow_detail_key") or "")
            workflow_key = str(card.property("workflow_key") or "")
            preset_id = str(card.property("workflow_preset_id") or "")
            title = getattr(card, "_workflow_title", None)
            detail = getattr(card, "_workflow_detail", None)
            runtime = getattr(card, "_workflow_runtime", None)
            open_button = getattr(card, "_workflow_open_button", None)
            compat_button = getattr(card, "_workflow_compat_button", None)
            preset_button = getattr(card, "_workflow_preset_button", None)
            if title is not None and title_key:
                title.setText(self.context.settings._tr(title_key))
            if detail is not None and detail_key:
                detail.setText(self.context.settings._tr(detail_key))
            if runtime is not None:
                runtime.setText(self.context.layout._workflow_runtime_status_text(workflow_key, preset_id))
            if open_button is not None:
                open_button.setText(self.context.settings._tr("workflow_card_open"))
            if compat_button is not None and title_key:
                compat_button.setText(self.context.settings._tr(title_key))
                compat_button.setToolTip(self.context.layout._media_start_button_tooltip(title_key, detail_key))
            if preset_button is not None:
                preset_button.setText(self.context.settings._tr("workflow_card_quick_preset"))
                preset_button.setToolTip(self.context.layout._workflow_preset_tooltip(workflow_key, preset_id))
        for button in self.context.get("_media_start_profile_buttons", {}).values():
            title_key = str(button.property("launcher_profile_title_key") or "")
            detail_key = str(button.property("launcher_profile_detail_key") or "")
            if title_key and detail_key:
                button.setText(self.context.settings._tr(title_key))
                button.setToolTip(self.context.layout._media_start_button_tooltip(title_key, detail_key))
        self.context.layout._sync_media_start_profile_buttons()
        self.context.layout._refresh_media_start_context()

    def _connect_media_start_context_refresh(self) -> None:
        if self.context.get("_media_start_context_refresh_connected", False):
            return
        self.context.layout._media_start_context_refresh_connected = True
        widgets = (
            self.context.get("_performance_preset_combo", None),
            self.context.get("_asr_provider_combo", None),
            self.context.get("_translator_combo", None),
            self.context.get("_tts_provider_combo", None),
            self.context.get("_audio_source_combo", None),
        )
        for widget in widgets:
            if widget is not None:
                widget.currentIndexChanged.connect(lambda *_args: self.context.layout._refresh_media_start_context())
        self.context.layout._refresh_media_start_context()

    def _refresh_media_start_context(self) -> None:
        edit = self.context.get("_media_start_quick_source_edit", None)
        if edit is not None:
            edit.setPlaceholderText(self.context.settings._tr("media_start_quick_placeholder"))
        recent_buttons = list(self.context.get("_media_start_recent_buttons", []) or [])
        recent_urls = list(self.context.sources._video_url_recent_urls_for_settings()[: len(recent_buttons)])
        empty_label = self.context.get("_media_start_recent_empty_label", None)
        if empty_label is not None:
            empty_label.setText(self.context.settings._tr("media_start_recent_empty"))
            empty_label.setVisible(not bool(recent_urls))
        for index, button in enumerate(recent_buttons):
            url = recent_urls[index] if index < len(recent_urls) else ""
            button.setProperty("source", url)
            if not url:
                button.hide()
                continue
            button.setText(self.context.layout._media_start_recent_source_label(url))
            button.setToolTip(url)
            button.show()
        summary = self.context.get("_media_start_config_summary", None)
        if summary is not None and self.context.has("_performance_preset_combo"):
            summary.setText(
                self.context.settings._tr("media_start_config_summary").format(
                    profile=self.context.user_guide._combo_text(self.context.layout._performance_preset_combo),
                    asr=self.context.user_guide._combo_text(self.context.layout._asr_provider_combo),
                    translation=self.context.user_guide._combo_text(self.context.layout._translator_combo),
                    tts=self.context.user_guide._combo_text(self.context.layout._tts_provider_combo),
                )
            )

    @staticmethod
    def _media_start_recent_source_label(source: str) -> str:
        return recent_source_label(source)

    def _media_start_button_tooltip(self, title_key: str, detail_key: str) -> str:
        return f"{self.context.settings._tr(title_key)}\n{self.context.settings._tr(detail_key)}"

    def _sync_media_start_profile_buttons(self) -> None:
        selected = str(self.context.get("_readiness_selected_profile", "auto") or "auto")
        for profile_key, button in self.context.get("_media_start_profile_buttons", {}).items():
            button.setChecked(profile_key == selected)

    def _sync_media_start_overlay(self) -> None:
        overlay = self.context.get("_media_start_overlay", None)
        media_stack = self.context.get("_media_stack", None)
        placeholder = self.context.get("_video_placeholder", None)
        start_page = self.context.get("_media_start_page", None)
        if overlay is None or media_stack is None or placeholder is None or start_page is None:
            return
        show = media_stack.currentWidget() is start_page
        overlay.setVisible(show)
        if show:
            overlay.raise_()

    def _apply_control_tooltips(self) -> None:
        tooltips = (
            ("_ui_language_combo", "language"),
            ("_aspect_combo", "video_aspect_tooltip"),
            ("_playback_quality_combo", "playback_quality_tooltip"),
            ("_subtitle_mode_combo", "subtitle_mode_tooltip"),
            ("_subtitle_size_combo", "subtitle_size_tooltip"),
            ("_subtitle_color_combo", "subtitle_color_tooltip"),
            ("_subtitle_background_combo", "subtitle_background_tooltip"),
            ("_position_slider", "playback_position_tooltip"),
            ("_volume_slider", "original_audio_volume_tooltip"),
            ("_dub_volume_slider", "dub_audio_volume_tooltip"),
            ("_audio_source_combo", "audio_source_tooltip"),
            ("_transcript_path_edit", "transcript_file_tooltip"),
            ("_transcript_file_button", "choose_transcript_title"),
            ("_source_language_combo", "source_language"),
            ("_target_language_combo", "target_language"),
            ("_asr_provider_combo", "asr_provider"),
            ("_asr_model_combo", "asr_model"),
            ("_asr_api_base_edit", "asr_api_base_placeholder"),
            ("_asr_language_hints_edit", "asr_language_hints_placeholder"),
            ("_asr_api_key_edit", "asr_api_key_placeholder"),
            ("_ocr_provider_combo", "ocr_provider"),
            ("_ocr_model_combo", "ocr_model"),
            ("_ocr_api_base_edit", "ocr_api_base_placeholder"),
            ("_ocr_api_key_edit", "ocr_api_key_placeholder"),
            ("_ocr_api_region_edit", "ocr_api_region_placeholder"),
            ("_ocr_timeout_slider", "ocr_timeout"),
            ("_ocr_fps_slider", "ocr_fps"),
            ("_ocr_crop_top_slider", "ocr_crop_top"),
            ("_ocr_crop_height_slider", "ocr_crop_height"),
            ("_ocr_scale_slider", "ocr_scale"),
            ("_ocr_psm_slider", "ocr_psm"),
            ("_ocr_threshold_check", "ocr_threshold"),
            ("_ocr_min_confidence_slider", "ocr_min_confidence"),
            ("_ocr_merge_similarity_slider", "ocr_merge_similarity"),
            ("_translator_combo", "translator"),
            ("_nllb_model_combo", "translation_model"),
            ("_translator_api_base_edit", "translator_api_base_placeholder"),
            ("_translator_api_key_edit", "translator_api_key_placeholder"),
            ("_translator_api_region_edit", "translator_api_region_placeholder"),
            ("_tts_api_base_edit", "tts_api_base_placeholder"),
            ("_tts_api_key_edit", "tts_api_key_placeholder"),
            ("_tts_api_secret_edit", "tts_api_secret_placeholder"),
            ("_tts_api_region_edit", "tts_api_region_placeholder"),
            ("_tts_model_edit", "tts_model_placeholder"),
            ("_speaker_gender_model_combo", "speaker_gender_model_tooltip"),
            ("_speaker_gender_provider_combo", "speaker_gender_provider"),
            ("_speaker_gender_api_base_edit", "speaker_gender_api_base_placeholder"),
            ("_speaker_gender_api_key_edit", "speaker_gender_api_key_placeholder"),
            ("_speaker_gender_timeout_slider", "speaker_gender_timeout"),
            ("_performance_preset_combo", "preset"),
            ("_export_video_quality_combo", "export_video_quality"),
            ("_translation_device_combo", "translator_device"),
            ("_whisper_offline_check", "whisper_offline"),
            ("_translation_offline_check", "translator_offline"),
            ("_vieneu_offline_check", "vieneu_offline"),
            ("_translation_max_tokens_slider", "translation_max_tokens"),
            ("_translation_beams_slider", "translation_beams"),
            ("_tts_provider_combo", "tts"),
            ("_vieneu_mode_combo", "mode"),
            ("_vieneu_model_combo", "model"),
            ("_vieneu_core_combo", "vieneu_core"),
            ("_tts_voice_combo", "voice_default"),
            ("_tts_male_voice_combo", "male_voice"),
            ("_tts_female_voice_combo", "female_voice"),
            ("_auto_voice_gender_check", "auto_gender"),
            ("_auto_voice_gender_mode_combo", "voice_gender_mode_tooltip"),
            ("_auto_match_audio_check", "auto_match"),
            ("_dubbing_buffer_slider", "buffer"),
            ("_dub_speed_slider", "speed"),
            ("_video_delay_slider", "video_delay"),
            ("_source_filter_check", "source_filter_tooltip"),
            ("_source_filter_mode_combo", "source_filter_mode_tooltip"),
            ("_source_filter_model_combo", "source_filter_model"),
            ("_video_url_full_cache_check", "video_url_full_cache_tooltip"),
            ("_video_cache_dir_edit", "video_cache_dir_tooltip"),
            ("_video_cache_dir_button", "video_cache_dir_choose"),
            ("_video_cache_dir_reset_button", "video_cache_dir_reset"),
            ("_whisper_device_combo", "whisper_device"),
            ("_whisper_compute_combo", "whisper_compute"),
            ("_whisper_beam_slider", "whisper_beam"),
            ("_whisper_vad_check", "whisper_vad_filter"),
            ("_segment_seconds_slider", "segment_length"),
            ("_prebuffer_segments_slider", "prebuffer_segments"),
            ("_lookahead_segments_slider", "lookahead_segments"),
            ("_overlap_policy_combo", "overlap_policy"),
            ("_start_delay_slider", "start_delay"),
            ("_speed_min_slider", "speed_min"),
            ("_speed_max_slider", "speed_max"),
            ("_volume_gain_min_slider", "gain_min"),
            ("_volume_gain_max_slider", "gain_max"),
            ("_vieneu_runtime_combo", "vieneu_runtime"),
            ("_vieneu_device_combo", "vieneu_device"),
            ("_vieneu_backend_combo", "vieneu_backend"),
            ("_vieneu_temperature_slider", "vieneu_temperature"),
            ("_vieneu_max_chars_slider", "tts_max_chars"),
            ("_vieneu_python_edit", "vieneu_python"),
            ("_capture_backend_combo", "capture_backend"),
            ("_capture_system_device_combo", "system_audio"),
            ("_capture_microphone_device_combo", "microphone"),
            ("_transcript_cleanup_mode_combo", "transcript_cleanup"),
            ("_transcript_cleanup_provider_combo", "cleanup_provider"),
            ("_transcript_cleanup_model_combo", "cleanup_model_tooltip"),
            ("_transcript_cleanup_api_base_edit", "cleanup_api_base_placeholder"),
            ("_transcript_cleanup_api_key_edit", "cleanup_api_key_placeholder"),
            ("_cleanup_timeout_slider", "cleanup_timeout"),
            ("_runtime_warmup_enabled_check", "runtime_warmup_enabled"),
            ("_runtime_warmup_whisper_check", "runtime_warmup_whisper"),
            ("_runtime_warmup_translation_check", "runtime_warmup_translation"),
            ("_runtime_warmup_tts_check", "runtime_warmup_tts"),
            ("_transcript_view_combo", "show_transcript"),
            ("_transcript_type_combo", "transcript_type"),
            ("_export_transcript_button", "export_transcript"),
            ("_document_view", "document_placeholder"),
            ("_transcript", "transcript_placeholder"),
            ("_offline_models_log", "offline_models_log_placeholder"),
        )
        for widget_name, key in tooltips:
            widget = self.context.get(widget_name, None)
            if widget is not None:
                self.context.ui._set_control_tooltip(widget, key)

    def _set_preserve_terms_tooltip(self) -> None:
        if not self.context.has("_preserve_terms_check"):
            return
        tooltip = self.context.settings._tr("preserved_terms_file_tooltip").format(
            path=self.context.config.preserved_source_terms_file
        )
        self.context.layout._preserve_terms_check.setToolTip(tooltip)
        if self.context.has("_preserved_terms_file_edit"):
            self.context.layout._preserved_terms_file_edit.setToolTip(tooltip)

    def _initial_capture_device_options(self) -> dict[str, list[str]]:
        return {
            "system": [self.context.config.capture_system_device] if self.context.config.capture_system_device else [],
            "microphone": [self.context.config.capture_microphone_device]
            if self.context.config.capture_microphone_device
            else [],
        }

    def _capture_devices_tab_changed(self, index: int) -> None:
        if not self.context.has("_advanced_tab_widget") or not self.context.has("_settings_tabs"):
            return
        if self.context.runtime._settings_tab_contains(
            self.context.layout._settings_tabs.widget(index), self.context.bindings._advanced_tab_widget
        ):
            self.context.layout._load_capture_device_options()

    def _load_capture_device_options(self, *, force: bool = False) -> None:
        if self.context.get("_capture_devices_loaded", False) and not force:
            return
        if not self.context.has("_capture_system_device_combo") or not self.context.has(
            "_capture_microphone_device_combo"
        ):
            return
        from ai_player.adapters.media.capture_sources import list_capture_device_options

        capture_devices = list_capture_device_options()
        self.context.layout._replace_capture_device_options(
            self.context.layout._capture_system_device_combo, capture_devices.get("system", [])
        )
        self.context.layout._replace_capture_device_options(
            self.context.layout._capture_microphone_device_combo,
            capture_devices.get("microphone", []),
        )
        self.context.layout._capture_devices_loaded = True

    def _replace_capture_device_options(self, combo: QComboBox, devices: list[str]) -> None:
        current = combo.currentData()
        was_blocked = combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.context.ui._i18n_text("auto"), "")
        seen = {""}
        for device in devices:
            device = str(device or "").strip()
            if not device or device in seen:
                continue
            combo.addItem(device, device)
            seen.add(device)
        if current and current not in seen:
            combo.addItem(str(current), current)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(was_blocked)
