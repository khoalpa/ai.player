from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPalette, QShortcut, QTextDocument
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEnginePage = None
    QWebEngineScript = None
    QWebEngineSettings = None
    QWebEngineView = None

from ai_player.core.runtime_catalog import (
    available_asr_models,
    available_gui_language_options,
    available_language_options,
    available_local_llm_options,
    available_ocr_models,
    available_ocr_providers,
    available_speaker_gender_models,
)
from ai_player.services.source_voice_filter import (
    SOURCE_VOICE_FILTER_DEMUCS_MODELS,
    normalize_source_voice_filter_model,
)
from ai_player.services.speaker_voice_selector import normalize_speaker_gender_provider, normalize_voice_gender_mode
from ai_player.services.tts_base import available_vieneu_modes
from ai_player.services.video_source import is_supported_browser_video_url
from ai_player.ui.player_window_media import DEFAULT_SIDEBAR_PANEL_SIZES
from ai_player.ui.player_window_media_browser import DEFAULT_MEDIA_HOME_URL, build_media_browser_buttons
from ai_player.ui.player_window_readiness import READINESS_PROFILES
from ai_player.ui.player_window_settings_tabs import (
    build_advanced_settings_tab,
    build_basic_settings_tab,
    build_models_settings_tab,
    build_settings_panel,
    build_settings_tabs,
    build_transcript_settings_tab,
)
from ai_player.ui.player_window_utils import (
    dropdown_options as _dropdown_options,
)
from ai_player.ui.player_window_utils import (
    ui_label as _ui_label,
)
from ai_player.ui.provider_preview_panel import add_provider_preview_row, build_provider_preview_panel

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


class PlayerLayoutMixin:
    def _build_ui(self) -> None:
        self._source_label = QLabel(self._tr("source_empty"))
        self._source_label.setObjectName("sourceLabel")
        self._source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._open_file_button = self._make_button(
            "open_video",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self._open_file_button.setObjectName("sourceButton")
        self._open_file_button.clicked.connect(lambda _checked=False: self._start_workflow("video", self._open_video))
        self._set_control_tooltip(self._open_file_button, "open_video_tooltip")
        self._open_url_button = self._make_button(
            "open_url",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._open_url_button.setObjectName("sourceButton")
        self._open_url_button.clicked.connect(lambda _checked=False: self._start_workflow("url", self._open_video_url))
        self._open_document_button = self._make_button(
            "open_document",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        self._open_document_button.setObjectName("sourceButton")
        self._open_document_button.clicked.connect(
            lambda _checked=False: self._start_workflow("document", self._open_document)
        )

        self._source_menu = QMenu(self)
        self._open_smart_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            self._tr("smart_open_files"),
            self,
        )
        self._open_smart_action.triggered.connect(self._open_smart_source)
        self._open_clipboard_source_action = QAction(self._tr("smart_open_clipboard"), self)
        self._open_clipboard_source_action.triggered.connect(self._open_smart_source_from_clipboard)
        self._open_paste_source_action = QAction(self._tr("smart_open_paste"), self)
        self._open_paste_source_action.triggered.connect(self._open_smart_source_prompt)
        self._open_video_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            self._tr("open_video"),
            self,
        )
        self._open_video_action.triggered.connect(
            lambda _checked=False: self._start_workflow("video", self._open_video)
        )
        self._open_url_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            self._tr("open_url"),
            self,
        )
        self._open_url_action.triggered.connect(
            lambda _checked=False: self._start_workflow("url", self._open_video_url)
        )
        self._open_document_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            self._tr("open_document"),
            self,
        )
        self._open_document_action.triggered.connect(
            lambda _checked=False: self._start_workflow("document", self._open_document)
        )
        self._source_menu.aboutToShow.connect(self._refresh_open_source_menu)
        self._source_menu.addAction(self._open_smart_action)
        self._source_menu.addAction(self._open_clipboard_source_action)
        self._source_menu.addAction(self._open_paste_source_action)
        self._open_source_button = self._make_button(
            "open_source",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self._open_source_button.setObjectName("sourceButton")
        self._open_source_button.setToolTip(self._tr("open_source_tooltip"))
        self._open_source_button.setProperty("i18n_tooltip_key", "open_source_tooltip")
        self._open_source_button.setMenu(self._source_menu)

        self._meeting_button = self._make_button(
            "start",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self._meeting_button.setObjectName("primaryButton")
        self._meeting_button.clicked.connect(
            lambda _checked=False: self._start_workflow("meeting", self._toggle_meeting)
        )
        self._ui_language_combo = QComboBox()
        self._compact_combo(self._ui_language_combo)
        self._ui_language_combo.setMinimumContentsLength(10)
        for option in available_gui_language_options():
            self._ui_language_combo.addItem(_ui_label(option.name), option.id)
        self._ui_language_combo.setCurrentIndex(max(0, self._ui_language_combo.findData(self._config.gui_language)))
        self._ui_language_combo.currentIndexChanged.connect(self._gui_language_changed)
        self._export_button = self._make_button(
            "export",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        self._export_button.setObjectName("primaryButton")
        self._export_button.clicked.connect(
            lambda _checked=False: self._start_workflow("export", self._run_contextual_export)
        )
        self._video_fullscreen_button = self._icon_button(QStyle.StandardPixmap.SP_TitleBarMaxButton, "fullscreen")
        self._video_fullscreen_button.setToolTip(self._tr("fullscreen_tooltip"))
        self._video_fullscreen_button.setProperty("i18n_tooltip_key", "fullscreen_tooltip")
        self._video_fullscreen_button.clicked.connect(self._toggle_video_fullscreen)
        self._focus_media_button = self._icon_button(QStyle.StandardPixmap.SP_TitleBarNormalButton, "focus_media")
        self._focus_media_button.setCheckable(True)
        self._focus_media_button.setToolTip(self._tr("focus_media_tooltip"))
        self._focus_media_button.setProperty("i18n_tooltip_key", "focus_media_tooltip")
        self._focus_media_button.clicked.connect(self._toggle_focus_media)
        self._panel_toggle_button = self._icon_button(QStyle.StandardPixmap.SP_TitleBarShadeButton, "panel_hide")
        self._panel_toggle_button.setToolTip(self._tr("panel_toggle_tooltip"))
        self._panel_toggle_button.setProperty("i18n_tooltip_key", "panel_toggle_tooltip")
        self._panel_toggle_button.clicked.connect(self._toggle_sidebar_panel)
        self._panel_expand_button = self._icon_button(QStyle.StandardPixmap.SP_ArrowLeft, "sidebar_wider")
        self._panel_expand_button.setToolTip(self._tr("sidebar_wider_tooltip"))
        self._panel_expand_button.setProperty("i18n_tooltip_key", "sidebar_wider_tooltip")
        self._panel_expand_button.clicked.connect(self._expand_sidebar_panel)
        self._panel_collapse_button = self._icon_button(QStyle.StandardPixmap.SP_ArrowRight, "sidebar_narrower")
        self._panel_collapse_button.setToolTip(self._tr("sidebar_narrower_tooltip"))
        self._panel_collapse_button.setProperty("i18n_tooltip_key", "sidebar_narrower_tooltip")
        self._panel_collapse_button.clicked.connect(self._collapse_sidebar_panel)
        self._layout_reset_button = self._icon_button(QStyle.StandardPixmap.SP_DialogResetButton, "reset")
        self._layout_reset_button.setToolTip(self._tr("reset_tooltip"))
        self._layout_reset_button.setProperty("i18n_tooltip_key", "reset_tooltip")
        self._layout_reset_button.clicked.connect(self._reset_app)
        self._help_button = self._icon_button(QStyle.StandardPixmap.SP_DialogHelpButton, "help")
        self._help_button.setToolTip(self._tr("help_tooltip"))
        self._help_button.setProperty("i18n_tooltip_key", "help_tooltip")
        self._help_button.clicked.connect(self._show_user_guide)
        self._top_panel_toggle_button = self._icon_button(
            QStyle.StandardPixmap.SP_ArrowUp,
            "top_panel_hide_tooltip",
        )
        self._top_panel_toggle_button.clicked.connect(self._toggle_top_panel)
        self._bottom_panel_toggle_button = self._icon_button(
            QStyle.StandardPixmap.SP_ArrowDown,
            "bottom_panel_hide_tooltip",
        )
        self._bottom_panel_toggle_button.clicked.connect(self._toggle_bottom_panel)
        self._right_panel_toggle_button = self._icon_button(
            QStyle.StandardPixmap.SP_ArrowRight,
            "right_panel_hide_tooltip",
        )
        self._right_panel_toggle_button.clicked.connect(self._toggle_sidebar_panel)

        self._simple_sidebar_enabled = True
        self._tools_menu = QMenu(self)
        self._simple_sidebar_action = QAction(self._tr("simple_sidebar_mode"), self)
        self._simple_sidebar_action.setCheckable(True)
        self._simple_sidebar_action.setChecked(True)
        self._simple_sidebar_action.toggled.connect(self._set_simple_sidebar_mode)
        self._task_center_action = QAction(self._tr("task_center_tab"), self)
        self._task_center_action.triggered.connect(
            lambda: self._select_settings_tab_for_widget(self._task_center_tab_widget)
        )
        self._offline_models_action = QAction(self._tr("offline_models_tab"), self)
        self._offline_models_action.triggered.connect(
            lambda: self._select_settings_tab_for_widget(self._offline_models_tab_widget)
        )
        self._advanced_settings_action = QAction(self._tr("advanced_tab"), self)
        self._advanced_settings_action.triggered.connect(
            lambda: self._select_settings_tab_for_widget(self._advanced_tab_widget)
        )
        self._runtime_details_action = QAction(self._tr("runtime_tab"), self)
        self._runtime_details_action.triggered.connect(
            lambda: self._select_settings_tab_for_widget(self._runtime_tab_widget)
        )
        self._workflow_health_action = QAction(self._tr("workflow_health_title"), self)
        self._workflow_health_action.triggered.connect(self._show_workflow_health)
        self._adult_health_action = QAction(self._tr("adult_health_title"), self)
        self._adult_health_action.triggered.connect(self._show_adult_extractor_health)
        self._adult_hosts_action = QAction(self._tr("adult_hosts_title"), self)
        self._adult_hosts_action.triggered.connect(self._show_adult_supported_hosts)
        self._cache_inspector_action = QAction(self._tr("cache_inspector_title"), self)
        self._cache_inspector_action.triggered.connect(self._show_cache_inspector)
        self._clear_workflow_cache_action = QAction(self._tr("task_center_clear_cache"), self)
        self._clear_workflow_cache_action.triggered.connect(self._clear_workflow_caches)
        self._fullscreen_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton),
            self._tr("fullscreen"),
            self,
        )
        self._fullscreen_action.triggered.connect(self._toggle_video_fullscreen)
        self._focus_media_action = QAction(
            self._app_icon("focus"),
            self._tr("focus_media"),
            self,
        )
        self._focus_media_action.setCheckable(True)
        self._focus_media_action.triggered.connect(self._toggle_focus_media)
        self._toggle_sidebar_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton),
            self._tr("panel_hide"),
            self,
        )
        self._toggle_sidebar_action.triggered.connect(self._toggle_sidebar_panel)
        self._sidebar_wider_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft),
            self._tr("sidebar_wider"),
            self,
        )
        self._sidebar_wider_action.triggered.connect(self._expand_sidebar_panel)
        self._sidebar_narrower_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            self._tr("sidebar_narrower"),
            self,
        )
        self._sidebar_narrower_action.triggered.connect(self._collapse_sidebar_panel)
        self._reset_layout_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            self._tr("reset"),
            self,
        )
        self._reset_layout_action.triggered.connect(self._reset_app)
        self._help_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton),
            self._tr("help"),
            self,
        )
        self._help_action.triggered.connect(self._show_user_guide)
        self._tools_menu.addAction(self._simple_sidebar_action)
        self._tools_menu.addSeparator()
        for action in (
            self._task_center_action,
            self._offline_models_action,
            self._advanced_settings_action,
            self._runtime_details_action,
            self._workflow_health_action,
            self._adult_health_action,
            self._adult_hosts_action,
            self._cache_inspector_action,
            self._clear_workflow_cache_action,
        ):
            self._tools_menu.addAction(action)
        self._tools_menu.addSeparator()
        for action in (
            self._fullscreen_action,
            self._focus_media_action,
            self._toggle_sidebar_action,
            self._sidebar_wider_action,
            self._sidebar_narrower_action,
            self._reset_layout_action,
            self._help_action,
        ):
            self._tools_menu.addAction(action)
        self._tools_menu_button = self._make_button(
            "tools_menu",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self._tools_menu_button.setObjectName("sourceButton")
        self._tools_menu_button.setToolTip(self._tr("tools_menu_tooltip"))
        self._tools_menu_button.setProperty("i18n_tooltip_key", "tools_menu_tooltip")
        self._tools_menu_button.setMenu(self._tools_menu)

        source_bar = QFrame()
        source_bar.setObjectName("sourceBar")
        self._source_bar = source_bar
        source_layout = QHBoxLayout(source_bar)
        source_layout.setContentsMargins(14, 9, 14, 9)
        source_layout.setSpacing(8)
        title = QLabel("AI Player")
        title.setObjectName("appTitle")
        source_layout.addWidget(title)
        source_layout.addWidget(self._source_label, 1)

        self._task_status_button = QPushButton(self._tr("task_status_idle"))
        self._task_status_button.setObjectName("taskStatusButton")
        self._task_status_button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        self._task_status_button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        self._task_status_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._task_status_button.setCursor(Qt.PointingHandCursor)
        self._task_status_button.setToolTip(self._tr("task_status_tooltip"))
        self._task_status_button.clicked.connect(self._toggle_task_drawer)
        source_layout.addWidget(self._task_status_button)

        source_actions = QFrame()
        source_actions.setObjectName("headerActionGroup")
        self._header_action_group = source_actions
        source_actions_layout = QHBoxLayout(source_actions)
        source_actions_layout.setContentsMargins(3, 3, 3, 3)
        source_actions_layout.setSpacing(3)
        source_actions_layout.addWidget(self._open_source_button)
        source_layout.addWidget(source_actions)

        primary_actions = QFrame()
        primary_actions.setObjectName("headerPrimaryGroup")
        self._header_primary_group = primary_actions
        primary_actions_layout = QHBoxLayout(primary_actions)
        primary_actions_layout.setContentsMargins(0, 0, 0, 0)
        primary_actions_layout.setSpacing(6)
        primary_actions_layout.addWidget(self._meeting_button)
        primary_actions_layout.addWidget(self._export_button)
        source_layout.addWidget(primary_actions)

        tools = QFrame()
        tools.setObjectName("headerToolGroup")
        self._header_tool_group = tools
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(3, 3, 3, 3)
        tools_layout.setSpacing(2)
        tools_layout.addWidget(self._tools_menu_button)
        source_layout.addWidget(tools)
        source_layout.addWidget(self._ui_language_combo)
        self._header_controls = (
            self._open_source_button,
            self._meeting_button,
            self._export_button,
            self._ui_language_combo,
            self._task_status_button,
            self._tools_menu_button,
            self._header_action_group,
            self._header_primary_group,
            self._header_tool_group,
        )

        self._video_widget = QVideoWidget()
        self._video_widget.setObjectName("videoSurface")
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)
        video_palette = self._video_widget.palette()
        video_palette.setColor(QPalette.Window, QColor("#ffffff"))
        video_palette.setColor(QPalette.Base, QColor("#ffffff"))
        self._video_widget.setPalette(video_palette)
        self._video_widget.setAttribute(Qt.WA_TranslucentBackground, False)
        self._video_widget.setAttribute(Qt.WA_NoSystemBackground, False)
        self._video_widget.setAutoFillBackground(True)
        self._video_widget.installEventFilter(self)
        self._telegram_video_widget = QVideoWidget()
        self._telegram_video_widget.setObjectName("telegramVideoSurface")
        self._telegram_video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._telegram_video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._telegram_video_widget.setPalette(video_palette)
        self._telegram_video_widget.setAttribute(Qt.WA_TranslucentBackground, False)
        self._telegram_video_widget.setAttribute(Qt.WA_NoSystemBackground, False)
        self._telegram_video_widget.setAutoFillBackground(True)
        self._telegram_video_widget.installEventFilter(self)
        if QWebEngineView is not None:
            if _InPlayerWebEngineView is not None:
                self._video_placeholder = _InPlayerWebEngineView()
            else:
                self._video_placeholder = QWebEngineView()
            if _InPlayerWebEnginePage is not None:
                self._video_placeholder.setPage(_InPlayerWebEnginePage(self._video_placeholder))
            self._video_placeholder.setUrl(QUrl(DEFAULT_MEDIA_HOME_URL))
        else:
            self._video_placeholder = QFrame()
        self._video_placeholder.setObjectName("videoPlaceholder")
        self._video_placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if hasattr(self._video_placeholder, "setAutoFillBackground"):
            self._video_placeholder.setAutoFillBackground(True)
        self._video_placeholder.installEventFilter(self)
        self._document_view = QTextEdit()
        self._document_view.setObjectName("documentView")
        self._document_view.setReadOnly(True)
        self._document_view.setFrameShape(QFrame.Shape.NoFrame)
        self._document_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._document_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._document_view.installEventFilter(self)
        self._document_view.document().setDocumentMargin(0)
        self._document_view.setPlaceholderText(self._tr("document_placeholder"))
        self._telegram_channel_view = QFrame()
        self._telegram_channel_view.setObjectName("telegramChannelView")
        self._telegram_channel_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._telegram_channel_view.installEventFilter(self)
        telegram_layout = QVBoxLayout(self._telegram_channel_view)
        telegram_layout.setContentsMargins(0, 0, 0, 0)
        telegram_layout.setSpacing(0)
        self._telegram_channel_title = QLabel(self._tr("telegram_channel_browser_title"))
        self._telegram_channel_title.setObjectName("telegramChannelTitle")
        self._telegram_channel_title.setWordWrap(True)
        self._telegram_channel_title.hide()
        self._telegram_channel_status = QLabel("")
        self._telegram_channel_status.setObjectName("telegramChannelStatus")
        self._telegram_channel_status.setWordWrap(True)
        self._telegram_channel_status.hide()
        telegram_tools = QHBoxLayout()
        telegram_tools.setContentsMargins(0, 0, 0, 0)
        telegram_tools.setSpacing(8)
        self._telegram_channel_search = QLineEdit()
        self._telegram_channel_search.setObjectName("telegramChannelSearch")
        self._telegram_channel_search.setFixedHeight(36)
        self._telegram_channel_search.setMinimumWidth(0)
        self._telegram_channel_search.setPlaceholderText(self._tr("telegram_channel_search"))
        self._telegram_channel_search.setProperty("i18n_key", "telegram_channel_search")
        self._telegram_channel_search.textChanged.connect(self._telegram_search_changed)
        self._telegram_channel_search.returnPressed.connect(self._search_current_telegram_channel_remote)
        self._telegram_channel_remote_search_button = QPushButton(self._tr("telegram_channel_remote_search"))
        self._telegram_channel_remote_search_button.setFixedSize(88, 36)
        self._telegram_channel_remote_search_button.setProperty("i18n_key", "telegram_channel_remote_search")
        self._telegram_channel_remote_search_button.clicked.connect(self._search_current_telegram_channel_remote)
        self._telegram_channel_filter_combo = QComboBox()
        self._telegram_channel_filter_combo.setObjectName("telegramChannelFilter")
        self._telegram_channel_filter_combo.setFixedSize(96, 36)
        for value, key in (
            ("all", "telegram_filter_all"),
            ("video", "telegram_filter_video"),
            ("photo", "telegram_filter_photo"),
            ("document", "telegram_filter_document"),
            ("audio", "telegram_filter_audio"),
            ("text", "telegram_filter_text"),
            ("blacklist", "telegram_filter_blacklist"),
        ):
            self._telegram_channel_filter_combo.addItem(self._tr(key), value)
        self._telegram_channel_filter_combo.currentIndexChanged.connect(self._telegram_filter_changed)
        self._telegram_channel_load_more_button = QPushButton(self._tr("telegram_channel_load_more"))
        self._telegram_channel_load_more_button.setFixedSize(96, 36)
        self._telegram_channel_load_more_button.setCheckable(True)
        self._telegram_channel_load_more_button.setProperty("i18n_key", "telegram_channel_load_more")
        self._telegram_channel_load_more_button.toggled.connect(self._telegram_load_more_toggled)
        self._telegram_channel_translate_button = QPushButton(self._tr("telegram_channel_translate"))
        self._telegram_channel_translate_button.setFixedSize(88, 36)
        self._telegram_channel_translate_button.setCheckable(True)
        self._telegram_channel_translate_button.setProperty("i18n_key", "telegram_channel_translate")
        self._telegram_channel_translate_button.toggled.connect(self._telegram_translation_toggled)
        self._telegram_channel_auto_open_check = QCheckBox(self._tr("telegram_channel_auto_open"))
        self._telegram_channel_auto_open_check.setObjectName("telegramChannelAutoOpen")
        self._telegram_channel_auto_open_check.setFixedHeight(36)
        self._telegram_channel_auto_open_check.setChecked(self._config.telegram_auto_open_videos)
        self._telegram_channel_auto_open_check.setProperty("i18n_key", "telegram_channel_auto_open")
        telegram_tools.addWidget(self._telegram_channel_search, 1)
        telegram_tools.addWidget(self._telegram_channel_remote_search_button)
        telegram_tools.addWidget(self._telegram_channel_filter_combo)
        telegram_tools.addWidget(self._telegram_channel_load_more_button)
        telegram_tools.addWidget(self._telegram_channel_translate_button)
        telegram_tools.addWidget(self._telegram_channel_auto_open_check)
        self._telegram_channel_list = QListWidget()
        self._telegram_channel_list.setObjectName("telegramChannelList")
        self._telegram_channel_list.setAlternatingRowColors(True)
        self._telegram_channel_list.setIconSize(QSize(96, 96))
        self._telegram_channel_list.setMinimumHeight(112)
        self._telegram_channel_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._telegram_channel_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._telegram_channel_list.setWordWrap(True)
        self._telegram_channel_list.setItemDelegate(TelegramChannelItemDelegate(self._telegram_channel_list))
        self._telegram_channel_list.installEventFilter(self)
        self._telegram_channel_list.viewport().installEventFilter(self)
        self._telegram_channel_list.currentItemChanged.connect(self._telegram_channel_selection_changed)
        self._telegram_channel_list.itemDoubleClicked.connect(self._telegram_channel_item_activated)
        self._telegram_channel_list.verticalScrollBar().valueChanged.connect(self._telegram_channel_scroll_changed)
        self._telegram_channel_preview = QTextEdit()
        self._telegram_channel_preview.setObjectName("telegramChannelPreview")
        self._telegram_channel_preview.setReadOnly(True)
        self._telegram_channel_preview.setMinimumHeight(160)
        self._telegram_channel_preview.setMaximumHeight(240)
        self._telegram_channel_preview.installEventFilter(self)
        self._telegram_channel_thumbnail = QLabel()
        self._telegram_channel_thumbnail.setObjectName("telegramChannelThumbnail")
        self._telegram_channel_thumbnail.setAlignment(Qt.AlignCenter)
        self._telegram_channel_thumbnail.setMinimumSize(320, 320)
        self._telegram_channel_thumbnail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._telegram_channel_thumbnail.setScaledContents(False)
        self._telegram_channel_thumbnail.installEventFilter(self)
        self._telegram_channel_thumbnail.setText("")
        self._telegram_channel_media_stack = QStackedWidget()
        self._telegram_channel_media_stack.setObjectName("telegramChannelMediaStack")
        self._telegram_channel_media_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._telegram_channel_media_stack.addWidget(self._telegram_channel_thumbnail)
        self._telegram_channel_media_stack.addWidget(self._telegram_video_widget)
        self._telegram_channel_media_panel = QFrame()
        self._telegram_channel_media_panel.setObjectName("telegramChannelMediaPanel")
        self._telegram_channel_media_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        telegram_media_layout = QGridLayout(self._telegram_channel_media_panel)
        telegram_media_layout.setContentsMargins(12, 12, 12, 12)
        telegram_media_layout.setSpacing(0)
        telegram_media_layout.addWidget(self._telegram_channel_media_stack, 0, 0)
        self._telegram_channel_side_toggle_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            "",
        )
        self._telegram_channel_side_toggle_button.setObjectName("telegramChannelSideToggle")
        self._telegram_channel_side_toggle_button.setFixedSize(36, 36)
        self._telegram_channel_side_toggle_button.setCheckable(True)
        self._telegram_channel_side_toggle_button.setChecked(True)
        self._telegram_channel_side_toggle_button.setCursor(Qt.PointingHandCursor)
        self._telegram_channel_side_toggle_button.toggled.connect(self._telegram_side_panel_toggled)
        telegram_media_layout.addWidget(
            self._telegram_channel_side_toggle_button,
            0,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        self._telegram_channel_side_toggle_button.raise_()
        self._telegram_channel_side_panel = QWidget()
        self._telegram_channel_side_panel.setObjectName("telegramChannelSidePanel")
        self._telegram_channel_side_panel.setMinimumWidth(320)
        self._telegram_channel_side_panel.setMaximumWidth(16777215)
        self._telegram_channel_open_button = QPushButton(
            self._tr("telegram_channel_open_item"),
            self._telegram_channel_side_panel,
        )
        self._telegram_channel_open_button.setProperty("i18n_key", "telegram_channel_open_item")
        self._telegram_channel_open_button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        self._telegram_channel_open_button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        self._telegram_channel_open_button.clicked.connect(self._open_selected_telegram_channel_item)
        self._telegram_channel_open_button.hide()
        self._telegram_channel_login_button = QPushButton(
            self._tr("telegram_channel_login"),
            self._telegram_channel_side_panel,
        )
        self._telegram_channel_login_button.setProperty("i18n_key", "telegram_channel_login")
        self._telegram_channel_login_button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        self._telegram_channel_login_button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        self._telegram_channel_login_button.clicked.connect(self._telegram_login_for_current_channel)
        self._telegram_channel_login_button.hide()
        self._telegram_channel_refresh_button = QPushButton(
            self._tr("telegram_channel_refresh"),
            self._telegram_channel_side_panel,
        )
        self._telegram_channel_refresh_button.setProperty("i18n_key", "telegram_channel_refresh")
        self._telegram_channel_refresh_button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        self._telegram_channel_refresh_button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        self._telegram_channel_refresh_button.clicked.connect(self._refresh_current_telegram_channel)
        self._telegram_channel_refresh_button.hide()
        telegram_side_layout = QVBoxLayout(self._telegram_channel_side_panel)
        telegram_side_layout.setContentsMargins(12, 12, 12, 12)
        telegram_side_layout.setSpacing(8)
        telegram_side_layout.addLayout(telegram_tools)
        telegram_side_layout.addWidget(self._telegram_channel_list, 1)
        telegram_side_layout.addWidget(self._telegram_channel_preview)
        self._telegram_channel_splitter = QSplitter(Qt.Horizontal)
        self._telegram_channel_splitter.setObjectName("telegramChannelSplitter")
        self._telegram_channel_splitter.addWidget(self._telegram_channel_media_panel)
        self._telegram_channel_splitter.addWidget(self._telegram_channel_side_panel)
        self._telegram_channel_splitter.setSizes([1, 1])
        self._telegram_channel_splitter.setStretchFactor(0, 1)
        self._telegram_channel_splitter.setStretchFactor(1, 1)
        self._telegram_channel_splitter.setCollapsible(0, False)
        self._telegram_channel_splitter.setCollapsible(1, False)
        self._telegram_channel_splitter.splitterMoved.connect(self._telegram_side_panel_splitter_moved)
        telegram_layout.addWidget(self._telegram_channel_splitter, 1)
        self._aspect_combo = self._option_combo(
            _dropdown_options("video_aspects", self._config.gui_language), DEFAULT_MEDIA_ASPECT_RATIO
        )
        self._aspect_combo.setFixedWidth(80)
        self._aspect_combo.currentIndexChanged.connect(self._video_aspect_changed)
        self._playback_quality_combo = self._option_combo(
            _dropdown_options("playback_video_qualities", self._config.gui_language),
            self._config.playback_video_quality,
        )
        self._playback_quality_combo.setFixedWidth(96)
        self._playback_quality_combo.currentIndexChanged.connect(self._playback_quality_changed)
        self._video_url_full_cache_check = QCheckBox(self._tr("video_url_full_cache"))
        self._video_url_full_cache_check.setProperty("i18n_key", "video_url_full_cache")
        self._video_url_full_cache_check.setChecked(self._config.video_url_full_cache)
        self._video_url_full_cache_check.setToolTip(self._tr("video_url_full_cache_tooltip"))
        self._video_url_full_cache_check.setProperty("i18n_tooltip_key", "video_url_full_cache_tooltip")
        self._video_cache_dir_edit = QLineEdit(self._config.video_cache_dir)
        self._video_cache_dir_edit.setPlaceholderText(self._tr("video_cache_dir_default"))
        self._video_cache_dir_edit.setProperty("i18n_key", "video_cache_dir_default")
        self._video_cache_dir_edit.editingFinished.connect(self._queue_save_settings)
        self._video_cache_dir_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            "",
        )
        self._video_cache_dir_button.setFixedSize(self._ICON_BUTTON_SIZE, self._ICON_BUTTON_SIZE)
        self._video_cache_dir_button.setToolTip(self._tr("video_cache_dir_choose"))
        self._video_cache_dir_button.setProperty("i18n_tooltip_key", "video_cache_dir_choose")
        self._video_cache_dir_button.clicked.connect(self._choose_video_cache_dir)
        self._video_cache_dir_reset_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            "",
        )
        self._video_cache_dir_reset_button.setFixedSize(self._ICON_BUTTON_SIZE, self._ICON_BUTTON_SIZE)
        self._video_cache_dir_reset_button.setToolTip(self._tr("video_cache_dir_reset"))
        self._video_cache_dir_reset_button.setProperty("i18n_tooltip_key", "video_cache_dir_reset")
        self._video_cache_dir_reset_button.clicked.connect(self._reset_video_cache_dir)
        self._media_stack = QStackedWidget()
        self._media_stack.setObjectName("mediaStack")
        self._media_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._media_start_page = QFrame()
        self._media_start_page.setObjectName("mediaStartPage")
        self._media_start_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        media_start_page_layout = QGridLayout(self._media_start_page)
        media_start_page_layout.setContentsMargins(0, 0, 0, 0)
        media_start_page_layout.setSpacing(0)
        self._media_start_content = self._media_start_panel()
        self._media_start_overlay = QScrollArea()
        self._media_start_overlay.setObjectName("mediaStartScroll")
        self._media_start_overlay.setWidgetResizable(True)
        self._media_start_overlay.setFrameShape(QFrame.Shape.NoFrame)
        self._media_start_overlay.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._media_start_overlay.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._media_start_overlay.setWidget(self._media_start_content)
        media_start_page_layout.addWidget(self._media_start_overlay, 0, 0)
        self._media_start_page.setAcceptDrops(True)
        self._media_start_overlay.setAcceptDrops(True)
        self._media_start_content.setAcceptDrops(True)
        self._media_start_page.installEventFilter(self)
        self._media_start_overlay.installEventFilter(self)
        self._media_start_content.installEventFilter(self)
        self._media_stack.addWidget(self._media_start_page)
        self._media_stack.addWidget(self._video_placeholder)
        self._media_stack.addWidget(self._video_widget)
        self._media_stack.addWidget(self._document_view)
        self._media_stack.addWidget(self._telegram_channel_view)
        self._media_stack.setCurrentWidget(self._media_start_page)
        self._media_stack.setAcceptDrops(True)
        self._media_stack.installEventFilter(self)
        self._media_frame = QFrame()
        self._media_frame.setObjectName("mediaFrame")
        self._media_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._media_frame.setAcceptDrops(True)
        self._media_frame.installEventFilter(self)
        media_frame_layout = QGridLayout(self._media_frame)
        media_frame_layout.setContentsMargins(0, 0, 0, 0)
        media_frame_layout.setSpacing(0)
        media_frame_layout.addWidget(self._media_stack, 0, 0)
        self._subtitle_overlay = SubtitleOverlayLabel()
        self._subtitle_overlay.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
            | Qt.BypassWindowManagerHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowStaysOnTopHint
        )
        self._subtitle_overlay.setObjectName("subtitleOverlay")
        self._subtitle_overlay.setAlignment(Qt.AlignCenter)
        self._subtitle_overlay.setWordWrap(True)
        self._subtitle_overlay.setTextFormat(Qt.PlainText)
        self._subtitle_overlay.setFrameStyle(QFrame.NoFrame)
        self._subtitle_overlay.setLineWidth(0)
        self._subtitle_overlay.setMidLineWidth(0)
        self._subtitle_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._subtitle_overlay.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._subtitle_overlay.setAttribute(Qt.WA_TranslucentBackground, True)
        self._subtitle_overlay.setAttribute(Qt.WA_NoSystemBackground, True)
        self._subtitle_overlay.setAttribute(Qt.WA_StyledBackground, False)
        self._subtitle_overlay.setAutoFillBackground(False)
        self._subtitle_overlay.hide()
        self._fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fullscreen_shortcut.setContext(Qt.ApplicationShortcut)
        self._fullscreen_shortcut.activated.connect(self._toggle_video_fullscreen)
        self._fullscreen_escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._fullscreen_escape_shortcut.setContext(Qt.ApplicationShortcut)
        self._fullscreen_escape_shortcut.activated.connect(self._handle_escape_shortcut)
        self._command_palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._command_palette_shortcut.setContext(Qt.ApplicationShortcut)
        self._command_palette_shortcut.activated.connect(self._show_command_palette)

        self._play_button = self._icon_button(QStyle.StandardPixmap.SP_MediaPlay, "play")
        self._play_button.clicked.connect(self._play)
        self._pause_button = self._icon_button(QStyle.StandardPixmap.SP_MediaPause, "pause")
        self._pause_button.clicked.connect(self._pause)
        self._stop_button = self._icon_button(QStyle.StandardPixmap.SP_MediaStop, "stop")
        self._stop_button.clicked.connect(self._stop)
        self._previous_page_button = self._icon_button(QStyle.StandardPixmap.SP_MediaSkipBackward, "previous")
        self._previous_page_button.clicked.connect(self._previous_media_item)
        self._next_page_button = self._icon_button(QStyle.StandardPixmap.SP_MediaSkipForward, "next")
        self._next_page_button.clicked.connect(self._next_media_item)
        build_media_browser_buttons(self)
        self._subtitle_mode_combo = QComboBox()
        self._subtitle_mode_combo.addItem("...", "off")
        self._subtitle_mode_combo.addItem(self._tr("source"), "source")
        self._subtitle_mode_combo.addItem(self._tr("target"), "target")
        self._subtitle_mode_combo.setCurrentIndex(max(0, self._subtitle_mode_combo.findData("target")))
        self._subtitle_mode_combo.setFixedWidth(80)
        self._subtitle_mode_combo.currentIndexChanged.connect(self._subtitle_mode_changed)
        self._subtitle_size_combo = QComboBox()
        self._subtitle_size_combo.addItem(self._tr("small"), 18)
        self._subtitle_size_combo.addItem(self._tr("medium"), 24)
        self._subtitle_size_combo.addItem(self._tr("large"), 32)
        self._subtitle_size_combo.addItem(self._tr("very_large"), 40)
        self._subtitle_size_combo.setCurrentIndex(max(0, self._subtitle_size_combo.findData(24)))
        self._subtitle_size_combo.setFixedWidth(80)
        self._subtitle_size_combo.currentIndexChanged.connect(self._subtitle_size_changed)
        self._subtitle_color_combo = QComboBox()
        self._subtitle_color_combo.addItem(self._tr("black"), "#000000")
        self._subtitle_color_combo.addItem(self._tr("white"), "#ffffff")
        self._subtitle_color_combo.addItem(self._tr("yellow"), "#ffd54a")
        self._subtitle_color_combo.addItem(self._tr("blue"), "#66d9ff")
        self._subtitle_color_combo.addItem(self._tr("green"), "#7ee787")
        self._subtitle_color_combo.addItem(self._tr("pink"), "#ff8bd1")
        self._subtitle_color_combo.setCurrentIndex(max(0, self._subtitle_color_combo.findData("#ffd54a")))
        self._subtitle_color_combo.setFixedWidth(80)
        self._subtitle_color_combo.currentIndexChanged.connect(self._subtitle_size_changed)
        self._subtitle_background_combo = QComboBox()
        self._subtitle_background_combo.addItem(self._tr("transparent"), "rgba(0, 0, 0, 0)")
        self._subtitle_background_combo.addItem(self._tr("black"), "rgba(0, 0, 0, 160)")
        self._subtitle_background_combo.addItem(self._tr("white"), "rgba(255, 255, 255, 190)")
        self._subtitle_background_combo.addItem(self._tr("yellow"), "rgba(255, 213, 74, 180)")
        self._subtitle_background_combo.addItem(self._tr("blue"), "rgba(102, 217, 255, 170)")
        self._subtitle_background_combo.addItem(self._tr("green"), "rgba(126, 231, 135, 170)")
        self._subtitle_background_combo.addItem(self._tr("pink"), "rgba(255, 139, 209, 170)")
        self._subtitle_background_combo.setCurrentIndex(0)
        self._subtitle_background_combo.setFixedWidth(112)
        self._subtitle_background_combo.setToolTip(self._tr("subtitle_background_tooltip"))
        self._subtitle_background_combo.setProperty("i18n_tooltip_key", "subtitle_background_tooltip")
        self._subtitle_background_combo.currentIndexChanged.connect(self._subtitle_size_changed)
        self._display_options_button = self._make_button(
            "display_options",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self._display_options_button.setObjectName("sourceButton")
        self._display_options_button.setCheckable(True)
        self._display_options_button.setToolTip(self._tr("display_options_tooltip"))
        self._display_options_button.setProperty("i18n_tooltip_key", "display_options_tooltip")
        self._display_options_button.toggled.connect(self._toggle_display_options)

        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 1000)
        self._position_slider.sliderPressed.connect(self._begin_seek)
        self._position_slider.sliderReleased.connect(self._end_seek)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setMinimumWidth(104)

        self._cache_status_panel = QFrame()
        self._cache_status_panel.setObjectName("cacheStatusPanel")
        cache_status_layout = QHBoxLayout(self._cache_status_panel)
        cache_status_layout.setContentsMargins(0, 0, 0, 0)
        cache_status_layout.setSpacing(8)
        self._cache_status_progress = QProgressBar()
        self._cache_status_progress.setRange(0, 100)
        self._cache_status_progress.setValue(0)
        self._cache_status_progress.setFixedWidth(180)
        self._cache_status_label = QLabel(self._tr("cache_status_starting"))
        self._cache_status_label.setWordWrap(False)
        self._cache_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._cache_play_now_button = QPushButton(self._tr("cache_play_now"))
        self._cache_play_now_button.setEnabled(False)
        self._cache_play_now_button.clicked.connect(self._play_video_url_stream_now)
        cache_status_layout.addWidget(self._cache_status_progress)
        cache_status_layout.addWidget(self._cache_status_label, 1)
        cache_status_layout.addWidget(self._cache_play_now_button)
        self._cache_status_panel.hide()

        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(self._config.original_audio_volume)
        self._volume_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._volume_slider.valueChanged.connect(self._set_volume)

        self._source_filter_check = QCheckBox(self._tr("source_filter"))
        self._source_filter_check.setProperty("i18n_key", "source_filter")
        self._source_filter_check.setChecked(self._config.original_audio_voice_filter)
        self._source_filter_check.setToolTip(self._tr("source_filter_tooltip"))
        self._source_filter_check.setProperty("i18n_tooltip_key", "source_filter_tooltip")
        self._source_filter_check.toggled.connect(self._source_voice_filter_changed)
        self._source_filter_mode_combo = QComboBox()
        self._source_filter_mode_combo.addItem(self._tr("source_filter_mode_fast"), "fast")
        self._source_filter_mode_combo.addItem(self._tr("source_filter_mode_ai"), "ai")
        self._source_filter_mode_combo.setCurrentIndex(
            max(0, self._source_filter_mode_combo.findData(self._config.original_audio_voice_filter_mode))
        )
        self._source_filter_mode_combo.setToolTip(self._tr("source_filter_mode_tooltip"))
        self._source_filter_mode_combo.setProperty("i18n_tooltip_key", "source_filter_mode_tooltip")
        self._source_filter_mode_combo.currentIndexChanged.connect(self._source_voice_filter_mode_changed)
        self._source_filter_model_combo = QComboBox()
        self._compact_combo(self._source_filter_model_combo)
        for model in sorted(SOURCE_VOICE_FILTER_DEMUCS_MODELS):
            self._source_filter_model_combo.addItem(model, model)
        selected_filter_model = normalize_source_voice_filter_model(self._config.original_audio_voice_filter_model)
        self._source_filter_model_combo.setCurrentIndex(
            max(0, self._source_filter_model_combo.findData(selected_filter_model))
        )
        self._source_filter_model_combo.currentIndexChanged.connect(self._source_voice_filter_mode_changed)

        self._dub_volume_slider = QSlider(Qt.Horizontal)
        self._dub_volume_slider.setRange(0, 100)
        self._dub_volume_slider.setValue(self._config.dubbing_voice_volume)
        self._dub_volume_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._dub_volume_slider.valueChanged.connect(self._set_dub_volume_status)

        controls = QFrame()
        controls.setObjectName("controls")
        controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._controls = controls
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 8, 12, 8)
        controls_layout.setSpacing(8)
        timeline_layout = QHBoxLayout()
        timeline_layout.setSpacing(6)
        timeline_layout.addWidget(self._position_slider, 1)
        timeline_layout.addWidget(self._time_label)
        timeline_layout.addWidget(self._audio_slider_control("original_audio", self._volume_slider))

        playback_layout = QHBoxLayout()
        playback_layout.setSpacing(6)
        playback_layout.addWidget(self._play_button)
        playback_layout.addWidget(self._pause_button)
        playback_layout.addWidget(self._stop_button)
        playback_layout.addWidget(self._previous_page_button)
        playback_layout.addWidget(self._next_page_button)
        playback_layout.addWidget(self._media_home_button)
        playback_layout.addWidget(self._telegram_browser_button)
        playback_layout.addWidget(self._display_options_button)
        playback_layout.addWidget(self._focus_media_button)
        playback_layout.addStretch(1)
        playback_layout.addWidget(self._audio_slider_control("dub_audio", self._dub_volume_slider))
        display_options = QFrame()
        display_options.setObjectName("displayOptionsPanel")
        self._display_options_panel = display_options
        display_options_layout = QHBoxLayout(display_options)
        display_options_layout.setContentsMargins(8, 6, 8, 6)
        display_options_layout.setSpacing(6)
        display_options_layout.addWidget(self._field_label("frame"))
        display_options_layout.addWidget(self._aspect_combo)
        display_options_layout.addWidget(self._playback_quality_combo)
        display_options_layout.addSpacing(6)
        display_options_layout.addWidget(self._field_label("subtitle"))
        display_options_layout.addWidget(self._subtitle_mode_combo)
        display_options_layout.addWidget(self._subtitle_size_combo)
        display_options_layout.addWidget(self._subtitle_color_combo)
        display_options_layout.addWidget(self._subtitle_background_combo)
        display_options_layout.addStretch(1)
        display_options.hide()
        controls_layout.addLayout(timeline_layout)
        controls_layout.addWidget(self._cache_status_panel)
        controls_layout.addLayout(playback_layout)
        controls_layout.addWidget(display_options)

        panel_visibility_bar = QFrame()
        panel_visibility_bar.setObjectName("panelVisibilityBar")
        self._panel_visibility_bar = panel_visibility_bar
        panel_visibility_layout = QHBoxLayout(panel_visibility_bar)
        panel_visibility_layout.setContentsMargins(0, 0, 0, 0)
        panel_visibility_layout.setSpacing(6)
        panel_visibility_layout.addStretch(1)
        panel_visibility_layout.addWidget(self._top_panel_toggle_button)
        panel_visibility_layout.addWidget(self._bottom_panel_toggle_button)
        panel_visibility_layout.addWidget(self._right_panel_toggle_button)
        self._panel_visibility_buttons = (
            self._top_panel_toggle_button,
            self._bottom_panel_toggle_button,
            self._right_panel_toggle_button,
        )

        video_panel = QFrame()
        video_panel.setObjectName("videoPanel")
        self._video_panel = video_panel
        video_layout = QVBoxLayout(video_panel)
        self._video_layout = video_layout
        video_layout.setContentsMargins(12, 12, 12, 12)
        video_layout.setSpacing(10)
        video_layout.addWidget(self._media_frame, 1, Qt.AlignCenter)
        video_layout.addWidget(panel_visibility_bar)
        video_layout.addWidget(controls)
        video_layout.setStretch(0, 1)
        video_layout.setStretch(1, 0)
        video_layout.setStretch(2, 0)

        self._dub_button = self._make_button(
            "dub_button",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume),
        )
        self._dub_button.setObjectName("dubButton")
        self._dub_button.setCheckable(True)
        self._dub_button.setChecked(self._dubbing_auto_enabled)
        self._dub_button.clicked.connect(self._toggle_dubbing)

        self._audio_source_combo = self._option_combo(
            _dropdown_options("audio_sources", self._config.gui_language),
            self._config.audio_source,
        )
        self._audio_source_combo.currentIndexChanged.connect(self._audio_source_changed)
        self._transcript_path_edit = QLineEdit(self._config.transcript_path)
        self._transcript_path_edit.setPlaceholderText(self._tr("transcript_file_placeholder"))
        self._transcript_path_edit.setClearButtonEnabled(True)
        self._transcript_path_edit.textEdited.connect(self._queue_save_settings)
        self._transcript_path_edit.textChanged.connect(self._invalidate_subtitle_entries)
        self._transcript_file_button = self._icon_button(QStyle.StandardPixmap.SP_FileDialogStart, "choose")
        self._transcript_file_button.clicked.connect(self._choose_transcript_file)

        self._source_language_combo = QComboBox()
        self._compact_combo(self._source_language_combo)
        for option in available_language_options(include_auto=True, language_id=self._config.gui_language):
            self._source_language_combo.addItem(_ui_label(option.name), option.id)
        self._source_language_combo.setCurrentIndex(
            max(0, self._source_language_combo.findData(self._config.source_language))
        )
        self._source_language_combo.currentIndexChanged.connect(self._language_pair_changed)
        self._target_language_combo = QComboBox()
        self._compact_combo(self._target_language_combo)
        for option in available_language_options(include_auto=False, language_id=self._config.gui_language):
            self._target_language_combo.addItem(_ui_label(option.name), option.id)
        self._target_language_combo.setCurrentIndex(
            max(0, self._target_language_combo.findData(self._config.target_language))
        )
        self._target_language_combo.currentIndexChanged.connect(self._language_pair_changed)

        self._advanced_provider_options_check = QCheckBox(self._tr("show_advanced_provider_options"))
        self._advanced_provider_options_check.setProperty("i18n_key", "show_advanced_provider_options")
        self._advanced_provider_options_check.setToolTip(self._tr("show_advanced_provider_options_tooltip"))
        self._advanced_provider_options_check.setProperty(
            "i18n_tooltip_key",
            "show_advanced_provider_options_tooltip",
        )
        self._advanced_provider_options_check.setChecked(self._config.show_advanced_provider_options)

        self._asr_provider_combo = QComboBox()
        self._compact_combo(self._asr_provider_combo)
        self._refresh_asr_provider_options()
        self._asr_model_combo = QComboBox()
        self._compact_combo(self._asr_model_combo)
        self._asr_model_combo.setEditable(True)
        for model in available_asr_models():
            self._asr_model_combo.addItem(model.name, model.id)
        asr_model_index = self._asr_model_combo.findData(self._config.whisper_model)
        if asr_model_index < 0 and self._config.whisper_model:
            self._asr_model_combo.addItem(self._config.whisper_model, self._config.whisper_model)
            asr_model_index = self._asr_model_combo.findData(self._config.whisper_model)
        self._asr_model_combo.setCurrentIndex(max(0, asr_model_index))
        self._asr_api_base_edit = QLineEdit(self._config.asr_api_base)
        self._asr_api_base_edit.setPlaceholderText(self._tr("asr_api_base_placeholder"))
        self._asr_language_hints_edit = QLineEdit(self._config.asr_language_hints)
        self._asr_language_hints_edit.setPlaceholderText(self._tr("asr_language_hints_placeholder"))
        self._asr_api_key_edit = QLineEdit(self._config.asr_api_key)
        self._asr_api_key_edit.setPlaceholderText(self._tr("asr_api_key_placeholder"))
        self._asr_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._asr_api_key_status = self._api_key_status_label()

        self._ocr_provider_combo = QComboBox()
        self._compact_combo(self._ocr_provider_combo)
        for provider in available_ocr_providers():
            self._ocr_provider_combo.addItem(provider.name, provider.id)
        self._ocr_provider_combo.setCurrentIndex(max(0, self._ocr_provider_combo.findData(self._config.ocr_provider)))
        self._ocr_model_combo = QComboBox()
        self._compact_combo(self._ocr_model_combo)
        self._ocr_model_combo.setEditable(True)
        for model in available_ocr_models():
            self._ocr_model_combo.addItem(model.name, model.id)
        ocr_model_index = self._ocr_model_combo.findData(self._config.ocr_model)
        if ocr_model_index < 0 and self._config.ocr_model:
            self._ocr_model_combo.addItem(self._config.ocr_model, self._config.ocr_model)
            ocr_model_index = self._ocr_model_combo.findData(self._config.ocr_model)
        self._ocr_model_combo.setCurrentIndex(max(0, ocr_model_index))
        self._ocr_api_base_edit = QLineEdit(self._config.ocr_api_base)
        self._ocr_api_base_edit.setPlaceholderText(self._tr("ocr_api_base_placeholder"))
        self._ocr_api_key_edit = QLineEdit(self._config.ocr_api_key)
        self._ocr_api_key_edit.setPlaceholderText(self._tr("ocr_api_key_placeholder"))
        self._ocr_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._ocr_api_key_status = self._api_key_status_label()
        self._ocr_api_region_edit = QLineEdit(self._config.ocr_api_region)
        self._ocr_api_region_edit.setPlaceholderText(self._tr("ocr_api_region_placeholder"))

        self._translator_combo = QComboBox()
        self._compact_combo(self._translator_combo)
        self._refresh_translation_provider_options()
        self._translator_combo.currentIndexChanged.connect(self._translator_changed)
        self._nllb_model_combo = QComboBox()
        self._compact_combo(self._nllb_model_combo)
        self._nllb_model_combo.setEditable(True)
        self._refresh_translation_models(self._config.local_translation_model)
        self._nllb_model_combo.currentIndexChanged.connect(self._nllb_model_changed)
        self._performance_preset_combo = self._option_combo(
            _dropdown_options("performance_presets", self._config.gui_language),
            self._config.performance_preset,
        )
        self._export_video_quality_combo = self._option_combo(
            _dropdown_options("video_qualities", self._config.gui_language),
            self._config.export_video_quality,
        )
        self._translation_device_combo = self._option_combo(
            _dropdown_options("translation_devices", self._config.gui_language),
            self._config.local_translation_device,
        )
        self._translator_api_base_edit = QLineEdit(self._config.translator_api_base)
        self._translator_api_base_edit.setPlaceholderText(self._tr("translator_api_base_placeholder"))
        self._translator_api_key_edit = QLineEdit(self._config.translator_api_key)
        self._translator_api_key_edit.setPlaceholderText(self._tr("translator_api_key_placeholder"))
        self._translator_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._translator_api_key_status = self._api_key_status_label()
        self._translator_api_region_edit = QLineEdit(self._config.translator_api_region)
        self._translator_api_region_edit.setPlaceholderText(self._tr("translator_api_region_placeholder"))
        self._preserve_terms_check = QCheckBox(self._tr("keep_terms"))
        self._preserve_terms_check.setProperty("i18n_key", "keep_terms")
        self._preserve_terms_check.setChecked(self._config.preserve_source_terms)
        self._set_preserve_terms_tooltip()
        self._preserved_terms_file_edit = QLineEdit(self._config.preserved_source_terms_file)
        self._preserved_terms_file_edit.setReadOnly(True)
        self._whisper_offline_check = QCheckBox(self._tr("whisper_offline"))
        self._whisper_offline_check.setProperty("i18n_key", "whisper_offline")
        self._whisper_offline_check.setChecked(self._config.whisper_offline)
        self._translation_offline_check = QCheckBox(self._tr("translator_offline"))
        self._translation_offline_check.setProperty("i18n_key", "translator_offline")
        self._translation_offline_check.setChecked(self._config.local_translation_offline)
        self._vieneu_offline_check = QCheckBox(self._tr("vieneu_offline"))
        self._vieneu_offline_check.setProperty("i18n_key", "vieneu_offline")
        self._vieneu_offline_check.setChecked(self._config.vieneu_tts_offline)
        self._translation_max_tokens_slider, self._translation_max_tokens_value = self._labeled_slider(
            minimum=64,
            maximum=512,
            step=32,
            value=self._config.translation_max_tokens,
            formatter=lambda value: f"{value}",
        )
        self._translation_beams_slider, self._translation_beams_value = self._labeled_slider(
            minimum=1,
            maximum=6,
            step=1,
            value=self._config.translation_num_beams,
            formatter=lambda value: f"{value}",
        )

        self._tts_provider_combo = QComboBox()
        self._compact_combo(self._tts_provider_combo)
        self._refresh_tts_provider_options()
        self._tts_provider_combo.currentIndexChanged.connect(self._refresh_tts_options)

        self._tts_mode_label = self._field_label("mode")
        self._vieneu_mode_combo = QComboBox()
        self._compact_combo(self._vieneu_mode_combo)
        for mode in available_vieneu_modes():
            self._vieneu_mode_combo.addItem(mode.name, mode.id)
        self._vieneu_mode_combo.setCurrentIndex(max(0, self._vieneu_mode_combo.findData(self._config.vieneu_tts_mode)))
        self._vieneu_mode_combo.currentIndexChanged.connect(self._refresh_vieneu_models)

        self._tts_model_label = self._field_label("model")
        self._vieneu_model_combo = QComboBox()
        self._compact_combo(self._vieneu_model_combo)
        self._vieneu_model_combo.currentIndexChanged.connect(self._refresh_tts_voices)

        self._tts_voice_combo = QComboBox()
        self._compact_combo(self._tts_voice_combo)
        self._tts_voice_combo.setEditable(True)
        self._tts_male_voice_combo = QComboBox()
        self._compact_combo(self._tts_male_voice_combo)
        self._tts_male_voice_combo.setEditable(True)
        self._tts_female_voice_combo = QComboBox()
        self._compact_combo(self._tts_female_voice_combo)
        self._tts_female_voice_combo.setEditable(True)
        self._tts_api_base_edit = QLineEdit(self._config.tts_api_base)
        self._tts_api_base_edit.setPlaceholderText(self._tr("tts_api_base_placeholder"))
        self._tts_api_key_edit = QLineEdit(self._config.tts_api_key)
        self._tts_api_key_edit.setPlaceholderText(self._tr("tts_api_key_placeholder"))
        self._tts_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._tts_api_key_status = self._api_key_status_label()
        self._tts_api_secret_edit = QLineEdit(self._config.tts_api_secret)
        self._tts_api_secret_edit.setPlaceholderText(self._tr("tts_api_secret_placeholder"))
        self._tts_api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._tts_api_secret_status = self._api_key_status_label()
        self._tts_api_region_edit = QLineEdit(self._config.tts_api_region)
        self._tts_api_region_edit.setPlaceholderText(self._tr("tts_api_region_placeholder"))
        self._tts_model_edit = QLineEdit(self._config.tts_model)
        self._tts_model_edit.setPlaceholderText(self._tr("tts_model_placeholder"))
        self._auto_voice_gender_check = QCheckBox(self._tr("auto_gender"))
        self._auto_voice_gender_check.setProperty("i18n_key", "auto_gender")
        self._auto_voice_gender_check.setChecked(self._config.dubbing_auto_voice_gender)
        self._auto_voice_gender_check.toggled.connect(self._sync_auto_voice_controls_enabled)
        self._auto_voice_gender_mode_combo = QComboBox()
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_balanced"), "balanced")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_ai"), "ai")
        self._auto_voice_gender_mode_combo.setCurrentIndex(
            max(
                0,
                self._auto_voice_gender_mode_combo.findData(
                    normalize_voice_gender_mode(self._config.dubbing_auto_voice_gender_mode)
                ),
            )
        )
        self._auto_voice_gender_mode_combo.setToolTip(self._tr("voice_gender_mode_tooltip"))
        self._auto_voice_gender_mode_combo.setProperty("i18n_tooltip_key", "voice_gender_mode_tooltip")
        self._auto_voice_gender_mode_combo.currentIndexChanged.connect(self._sync_auto_voice_controls_enabled)
        self._speaker_gender_model_combo = QComboBox()
        self._compact_combo(self._speaker_gender_model_combo)
        self._speaker_gender_model_combo.setEditable(True)
        for model in available_speaker_gender_models():
            self._speaker_gender_model_combo.addItem(model.name, model.id)
        speaker_gender_model_index = self._speaker_gender_model_combo.findData(self._config.speaker_gender_model)
        if speaker_gender_model_index < 0 and self._config.speaker_gender_model:
            self._speaker_gender_model_combo.addItem(
                self._config.speaker_gender_model,
                self._config.speaker_gender_model,
            )
            speaker_gender_model_index = self._speaker_gender_model_combo.findData(self._config.speaker_gender_model)
        self._speaker_gender_model_combo.setCurrentIndex(max(0, speaker_gender_model_index))
        self._speaker_gender_model_combo.setToolTip(self._tr("speaker_gender_model_tooltip"))
        self._speaker_gender_model_combo.setProperty("i18n_tooltip_key", "speaker_gender_model_tooltip")
        self._speaker_gender_provider_combo = QComboBox()
        self._compact_combo(self._speaker_gender_provider_combo)
        self._speaker_gender_provider_combo.addItem(self._tr("speaker_gender_provider_local"), "local")
        self._speaker_gender_provider_combo.setCurrentIndex(
            max(
                0,
                self._speaker_gender_provider_combo.findData(
                    normalize_speaker_gender_provider(self._config.speaker_gender_provider)
                ),
            )
        )
        self._speaker_gender_api_base_edit = QLineEdit(self._config.speaker_gender_api_base)
        self._speaker_gender_api_base_edit.setPlaceholderText(self._tr("speaker_gender_api_base_placeholder"))
        self._speaker_gender_api_key_edit = QLineEdit(self._config.speaker_gender_api_key)
        self._speaker_gender_api_key_edit.setPlaceholderText(self._tr("speaker_gender_api_key_placeholder"))
        self._speaker_gender_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._speaker_gender_api_key_status = self._api_key_status_label()
        self._speaker_gender_timeout_slider, self._speaker_gender_timeout_value = self._labeled_slider(
            minimum=3,
            maximum=120,
            step=1,
            value=int(self._config.speaker_gender_timeout_seconds),
            formatter=lambda value: f"{value} s",
        )
        self._auto_match_audio_check = QCheckBox(self._tr("auto_match"))
        self._auto_match_audio_check.setProperty("i18n_key", "auto_match")
        self._auto_match_audio_check.setChecked(self._config.dubbing_auto_match_audio)
        self._dubbing_buffer_slider = self._value_slider(
            minimum=0,
            maximum=600,
            step=10,
            value=int(self._config.dubbing_min_ready_ahead_seconds),
        )
        self._dubbing_buffer_value = self._value_label(f"{int(self._config.dubbing_min_ready_ahead_seconds)} s")
        self._dubbing_buffer_slider.valueChanged.connect(lambda value: self._dubbing_buffer_value.setText(f"{value} s"))
        self._dub_speed_slider = self._value_slider(
            minimum=-20,
            maximum=20,
            step=5,
            value=self._config.dubbing_speed_percent,
        )
        self._dub_speed_value = self._value_label(f"{self._config.dubbing_speed_percent:+d} %")
        self._dub_speed_slider.valueChanged.connect(lambda value: self._dub_speed_value.setText(f"{value:+d} %"))
        self._video_delay_slider = self._value_slider(
            minimum=0,
            maximum=30,
            step=1,
            value=int(self._config.original_audio_playback_delay_seconds),
        )
        self._video_delay_value = self._value_label(f"{int(self._config.original_audio_playback_delay_seconds)} s")
        self._video_delay_slider.valueChanged.connect(lambda value: self._video_delay_value.setText(f"{value} s"))
        self._whisper_device_combo = self._option_combo(
            _dropdown_options("whisper_devices", self._config.gui_language),
            self._config.whisper_device,
        )
        self._whisper_compute_combo = self._option_combo(
            _dropdown_options("whisper_compute_types", self._config.gui_language),
            self._config.whisper_compute_type,
        )
        self._whisper_beam_slider, self._whisper_beam_value = self._labeled_slider(
            minimum=1,
            maximum=8,
            step=1,
            value=self._config.whisper_beam_size,
            formatter=lambda value: f"{value}",
        )
        self._whisper_vad_check = QCheckBox(self._tr("whisper_vad_filter"))
        self._whisper_vad_check.setProperty("i18n_key", "whisper_vad_filter")
        self._whisper_vad_check.setChecked(self._config.whisper_vad_filter)
        self._segment_seconds_slider, self._segment_seconds_value = self._labeled_slider(
            minimum=4,
            maximum=20,
            step=2,
            value=self._config.segment_seconds,
            formatter=lambda value: f"{value} s",
        )
        self._prebuffer_segments_slider, self._prebuffer_segments_value = self._labeled_slider(
            minimum=1,
            maximum=4,
            step=1,
            value=self._config.dubbing_prebuffer_segments,
            formatter=lambda value: f"{value}",
        )
        self._lookahead_segments_slider, self._lookahead_segments_value = self._labeled_slider(
            minimum=1,
            maximum=6,
            step=1,
            value=self._config.dubbing_lookahead_segments,
            formatter=lambda value: f"{value}",
        )
        self._overlap_policy_combo = self._option_combo(
            _dropdown_options("dubbing_overlap_policies", self._config.gui_language),
            self._config.dubbing_overlap_policy,
        )
        self._start_delay_slider, self._start_delay_value = self._labeled_slider(
            minimum=0,
            maximum=5,
            step=1,
            value=int(self._config.dubbing_start_delay_seconds),
            formatter=lambda value: f"{value} s",
        )
        self._speed_min_slider, self._speed_min_value = self._labeled_slider(
            minimum=80,
            maximum=100,
            step=5,
            value=int(self._config.dubbing_speed_min * 100),
            formatter=lambda value: f"{value} %",
        )
        self._speed_max_slider, self._speed_max_value = self._labeled_slider(
            minimum=100,
            maximum=125,
            step=5,
            value=int(self._config.dubbing_speed_max * 100),
            formatter=lambda value: f"{value} %",
        )
        self._volume_gain_min_slider, self._volume_gain_min_value = self._labeled_slider(
            minimum=-20,
            maximum=0,
            step=1,
            value=int(self._config.dubbing_volume_gain_min_db),
            formatter=lambda value: f"{value} dB",
        )
        self._volume_gain_max_slider, self._volume_gain_max_value = self._labeled_slider(
            minimum=0,
            maximum=20,
            step=1,
            value=int(self._config.dubbing_volume_gain_max_db),
            formatter=lambda value: f"+{value} dB",
        )
        self._vieneu_runtime_combo = self._option_combo(
            _dropdown_options("vieneu_runtimes", self._config.gui_language),
            self._config.vieneu_tts_runtime,
        )
        self._vieneu_device_combo = self._option_combo(
            _dropdown_options("vieneu_devices", self._config.gui_language),
            self._config.vieneu_tts_device,
        )
        self._vieneu_backend_combo = self._option_combo(
            _dropdown_options("vieneu_backends", self._config.gui_language),
            self._config.vieneu_tts_backend,
        )
        self._capture_devices_loaded = False
        capture_devices = self._initial_capture_device_options()
        self._capture_backend_combo = self._option_combo(
            _dropdown_options("capture_backends", self._config.gui_language),
            self._config.capture_backend,
        )
        self._capture_system_device_combo = self._device_combo(
            capture_devices.get("system", []),
            self._config.capture_system_device,
        )
        self._capture_microphone_device_combo = self._device_combo(
            capture_devices.get("microphone", []),
            self._config.capture_microphone_device,
        )
        self._transcript_cleanup_mode_combo = self._option_combo(
            _dropdown_options("transcript_cleanup_modes", self._config.gui_language),
            self._config.transcript_cleanup_mode,
        )
        self._transcript_cleanup_provider_combo = self._option_combo(
            _dropdown_options("transcript_cleanup_providers", self._config.gui_language),
            self._config.transcript_cleanup_provider,
        )
        self._transcript_cleanup_model_combo = QComboBox()
        self._compact_combo(self._transcript_cleanup_model_combo)
        self._transcript_cleanup_model_combo.setEditable(True)
        for option in available_local_llm_options():
            self._transcript_cleanup_model_combo.addItem(option.name, option.id)
        current_cleanup_model = self._config.transcript_cleanup_model
        cleanup_model_index = self._transcript_cleanup_model_combo.findData(current_cleanup_model)
        if cleanup_model_index < 0 and current_cleanup_model:
            self._transcript_cleanup_model_combo.addItem(current_cleanup_model, current_cleanup_model)
            cleanup_model_index = self._transcript_cleanup_model_combo.findData(current_cleanup_model)
        self._transcript_cleanup_model_combo.setCurrentIndex(max(0, cleanup_model_index))
        self._transcript_cleanup_model_combo.setToolTip(self._tr("cleanup_model_tooltip"))
        self._transcript_cleanup_api_base_edit = QLineEdit(self._config.transcript_cleanup_api_base)
        self._transcript_cleanup_api_base_edit.setPlaceholderText(self._tr("cleanup_api_base_placeholder"))
        self._transcript_cleanup_api_key_edit = QLineEdit(self._config.transcript_cleanup_api_key)
        self._transcript_cleanup_api_key_edit.setPlaceholderText(self._tr("cleanup_api_key_placeholder"))
        self._transcript_cleanup_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._transcript_cleanup_api_key_status = self._api_key_status_label()
        self._cleanup_timeout_slider, self._cleanup_timeout_value = self._labeled_slider(
            minimum=1,
            maximum=120,
            step=1,
            value=int(self._config.transcript_cleanup_timeout_seconds),
            formatter=lambda value: f"{value} s",
        )
        self._transcript_cleanup_mode_combo.currentIndexChanged.connect(self._sync_transcript_cleanup_controls)
        self._transcript_cleanup_provider_combo.currentIndexChanged.connect(self._sync_transcript_cleanup_controls)
        self._vieneu_temperature_slider, self._vieneu_temperature_value = self._labeled_slider(
            minimum=0,
            maximum=100,
            step=5,
            value=int(self._config.vieneu_tts_temperature * 100),
            formatter=lambda value: f"{value / 100:.2f}",
        )
        self._vieneu_max_chars_slider, self._vieneu_max_chars_value = self._labeled_slider(
            minimum=80,
            maximum=320,
            step=20,
            value=self._config.vieneu_tts_max_chars_chunk,
            formatter=lambda value: f"{value}",
        )
        self._runtime_warmup_enabled_check = QCheckBox(self._tr("runtime_warmup_enabled"))
        self._runtime_warmup_enabled_check.setProperty("i18n_key", "runtime_warmup_enabled")
        self._runtime_warmup_enabled_check.setChecked(self._config.runtime_warmup_enabled)
        self._runtime_warmup_whisper_check = QCheckBox(self._tr("runtime_warmup_whisper"))
        self._runtime_warmup_whisper_check.setProperty("i18n_key", "runtime_warmup_whisper")
        self._runtime_warmup_whisper_check.setChecked(self._config.runtime_warmup_whisper)
        self._runtime_warmup_translation_check = QCheckBox(self._tr("runtime_warmup_translation"))
        self._runtime_warmup_translation_check.setProperty("i18n_key", "runtime_warmup_translation")
        self._runtime_warmup_translation_check.setChecked(self._config.runtime_warmup_translation)
        self._runtime_warmup_tts_check = QCheckBox(self._tr("runtime_warmup_tts"))
        self._runtime_warmup_tts_check.setProperty("i18n_key", "runtime_warmup_tts")
        self._runtime_warmup_tts_check.setChecked(self._config.runtime_warmup_tts)

        self._ocr_fps_slider, self._ocr_fps_value = self._labeled_slider(
            minimum=2,
            maximum=100,
            step=1,
            value=int(self._config.ocr_fps * 10),
            formatter=lambda value: f"{value / 10:.1f}",
        )
        self._ocr_crop_top_slider, self._ocr_crop_top_value = self._labeled_slider(
            minimum=0,
            maximum=95,
            step=1,
            value=int(self._config.ocr_crop_top_ratio * 100),
            formatter=lambda value: f"{value} %",
        )
        self._ocr_crop_height_slider, self._ocr_crop_height_value = self._labeled_slider(
            minimum=5,
            maximum=100,
            step=1,
            value=int(self._config.ocr_crop_height_ratio * 100),
            formatter=lambda value: f"{value} %",
        )
        self._ocr_scale_slider, self._ocr_scale_value = self._labeled_slider(
            minimum=100,
            maximum=400,
            step=25,
            value=int(self._config.ocr_scale * 100),
            formatter=lambda value: f"{value / 100:.2f}x",
        )
        self._ocr_psm_slider, self._ocr_psm_value = self._labeled_slider(
            minimum=3,
            maximum=13,
            step=1,
            value=int(self._config.ocr_psm),
            formatter=lambda value: f"{value}",
        )
        self._ocr_threshold_check = QCheckBox(self._tr("ocr_threshold"))
        self._ocr_threshold_check.setProperty("i18n_key", "ocr_threshold")
        self._ocr_threshold_check.setChecked(self._config.ocr_threshold)
        self._ocr_min_confidence_slider, self._ocr_min_confidence_value = self._labeled_slider(
            minimum=0,
            maximum=100,
            step=5,
            value=int(self._config.ocr_min_confidence),
            formatter=lambda value: f"{value} %",
        )
        self._ocr_merge_similarity_slider, self._ocr_merge_similarity_value = self._labeled_slider(
            minimum=0,
            maximum=100,
            step=1,
            value=int(self._config.ocr_merge_similarity * 100),
            formatter=lambda value: f"{value} %",
        )
        self._ocr_timeout_slider, self._ocr_timeout_value = self._labeled_slider(
            minimum=3,
            maximum=180,
            step=1,
            value=int(self._config.ocr_timeout_seconds),
            formatter=lambda value: f"{value} s",
        )

        self._vieneu_core_combo = QComboBox()
        self._compact_combo(self._vieneu_core_combo)
        self._vieneu_core_combo.addItem(self._tr("vieneu_core_local"), "local")
        self._vieneu_core_combo.setCurrentIndex(0)
        self._vieneu_path_edit = QLineEdit(self._config.vieneu_tts_path)
        self._vieneu_python_edit = QLineEdit(self._config.vieneu_tts_python)
        self._vieneu_api_base_edit = QLineEdit("")
        self._vieneu_api_base_edit.setEnabled(False)
        self._vieneu_decoder_path_edit = QLineEdit(self._config.vieneu_tts_decoder_path)
        self._vieneu_encoder_path_edit = QLineEdit(self._config.vieneu_tts_encoder_path)
        self._vieneu_standard_codec_path_edit = QLineEdit(self._config.vieneu_tts_standard_codec_path)
        build_provider_preview_panel(self)

        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(8)
        preset_layout.addWidget(self._field_label("preset"))
        preset_layout.addWidget(self._performance_preset_combo, 1)
        self._preset_inspector = QLabel("")
        self._preset_inspector.setObjectName("presetInspector")
        self._preset_inspector.setWordWrap(True)
        self._preset_cards = {}
        self._preset_cards_panel = self._preset_cards_panel_widget()

        basic_source_grid = QGridLayout()
        basic_source_grid.setHorizontalSpacing(8)
        basic_source_grid.setVerticalSpacing(7)
        basic_source_grid.addWidget(preset_row, 0, 0, 1, 2)
        basic_source_grid.addWidget(self._preset_inspector, 1, 0, 1, 2)
        basic_source_grid.addWidget(self._preset_cards_panel, 2, 0, 1, 2)
        basic_source_grid.addWidget(self._audio_source_panel(), 3, 0, 1, 2)
        basic_source_grid.addWidget(self._field_label("source_language"), 4, 0)
        basic_source_grid.addWidget(self._source_language_combo, 4, 1)
        basic_source_grid.addWidget(self._field_label("target_language"), 5, 0)
        basic_source_grid.addWidget(self._target_language_combo, 5, 1)

        basic_voice_grid = QGridLayout()
        basic_voice_grid.setHorizontalSpacing(8)
        basic_voice_grid.setVerticalSpacing(7)
        basic_voice_grid.addWidget(self._field_label("voice_default"), 0, 0)
        basic_voice_grid.addWidget(self._tts_voice_combo, 0, 1)
        basic_voice_grid.addWidget(self._auto_voice_gender_check, 1, 0, 1, 2)
        basic_voice_grid.addWidget(self._field_label("voice_gender_mode"), 2, 0)
        basic_voice_grid.addWidget(self._auto_voice_gender_mode_combo, 2, 1)
        basic_voice_grid.addWidget(self._field_label("male_voice"), 3, 0)
        basic_voice_grid.addWidget(self._tts_male_voice_combo, 3, 1)
        basic_voice_grid.addWidget(self._field_label("female_voice"), 4, 0)
        basic_voice_grid.addWidget(self._tts_female_voice_combo, 4, 1)

        basic_playback_grid = QGridLayout()
        basic_playback_grid.setHorizontalSpacing(8)
        basic_playback_grid.setVerticalSpacing(7)
        basic_playback_grid.addWidget(self._field_label("buffer"), 0, 0)
        basic_playback_grid.addWidget(
            self._slider_row(self._dubbing_buffer_slider, self._dubbing_buffer_value), 0, 1
        )
        basic_playback_grid.addWidget(self._field_label("speed"), 1, 0)
        basic_playback_grid.addWidget(self._slider_row(self._dub_speed_slider, self._dub_speed_value), 1, 1)
        basic_playback_grid.addWidget(self._field_label("video_delay"), 2, 0)
        basic_playback_grid.addWidget(self._slider_row(self._video_delay_slider, self._video_delay_value), 2, 1)

        basic_processing_grid = QGridLayout()
        basic_processing_grid.setHorizontalSpacing(8)
        basic_processing_grid.setVerticalSpacing(7)
        basic_processing_grid.addWidget(self._source_filter_check, 0, 0, 1, 2)
        basic_processing_grid.addWidget(self._field_label("source_filter_provider"), 1, 0)
        basic_processing_grid.addWidget(self._source_filter_mode_combo, 1, 1)
        basic_processing_grid.addWidget(self._field_label("export_video_quality"), 2, 0)
        basic_processing_grid.addWidget(self._export_video_quality_combo, 2, 1)
        basic_processing_grid.addWidget(self._video_url_full_cache_check, 3, 0, 1, 2)
        basic_processing_grid.addWidget(self._field_label("video_cache_dir"), 4, 0)
        video_cache_dir_row = QWidget()
        video_cache_dir_layout = QHBoxLayout(video_cache_dir_row)
        video_cache_dir_layout.setContentsMargins(0, 0, 0, 0)
        video_cache_dir_layout.setSpacing(6)
        video_cache_dir_layout.addWidget(self._video_cache_dir_edit, 1)
        video_cache_dir_layout.addWidget(self._video_cache_dir_button)
        video_cache_dir_layout.addWidget(self._video_cache_dir_reset_button)
        basic_processing_grid.addWidget(video_cache_dir_row, 4, 1)

        advanced_terms_grid = QGridLayout()
        advanced_terms_grid.setHorizontalSpacing(8)
        advanced_terms_grid.setVerticalSpacing(7)
        advanced_terms_grid.addWidget(self._preserve_terms_check, 0, 0, 1, 2)
        advanced_terms_grid.addWidget(self._field_label("preserved_terms"), 1, 0)
        advanced_terms_grid.addWidget(self._preserved_terms_file_edit, 1, 1)

        advanced_timing_grid = QGridLayout()
        advanced_timing_grid.setHorizontalSpacing(8)
        advanced_timing_grid.setVerticalSpacing(7)
        advanced_timing_grid.addWidget(self._field_label("segment_length"), 0, 0)
        advanced_timing_grid.addWidget(
            self._slider_row(self._segment_seconds_slider, self._segment_seconds_value), 0, 1
        )
        advanced_timing_grid.addWidget(self._field_label("prebuffer_segments"), 1, 0)
        advanced_timing_grid.addWidget(
            self._slider_row(self._prebuffer_segments_slider, self._prebuffer_segments_value), 1, 1
        )
        advanced_timing_grid.addWidget(self._field_label("lookahead_segments"), 2, 0)
        advanced_timing_grid.addWidget(
            self._slider_row(self._lookahead_segments_slider, self._lookahead_segments_value), 2, 1
        )

        advanced_match_grid = QGridLayout()
        advanced_match_grid.setHorizontalSpacing(8)
        advanced_match_grid.setVerticalSpacing(7)
        advanced_match_grid.addWidget(self._auto_match_audio_check, 0, 0, 1, 2)
        advanced_match_grid.addWidget(self._field_label("speed_min"), 1, 0)
        advanced_match_grid.addWidget(self._slider_row(self._speed_min_slider, self._speed_min_value), 1, 1)
        advanced_match_grid.addWidget(self._field_label("speed_max"), 2, 0)
        advanced_match_grid.addWidget(self._slider_row(self._speed_max_slider, self._speed_max_value), 2, 1)
        advanced_match_grid.addWidget(self._field_label("gain_min"), 3, 0)
        advanced_match_grid.addWidget(self._slider_row(self._volume_gain_min_slider, self._volume_gain_min_value), 3, 1)
        advanced_match_grid.addWidget(self._field_label("gain_max"), 4, 0)
        advanced_match_grid.addWidget(self._slider_row(self._volume_gain_max_slider, self._volume_gain_max_value), 4, 1)

        advanced_playback_grid = QGridLayout()
        advanced_playback_grid.setHorizontalSpacing(8)
        advanced_playback_grid.setVerticalSpacing(7)
        advanced_playback_grid.addWidget(self._field_label("overlap_policy"), 0, 0)
        advanced_playback_grid.addWidget(self._overlap_policy_combo, 0, 1)
        advanced_playback_grid.addWidget(self._field_label("start_delay"), 1, 0)
        advanced_playback_grid.addWidget(self._slider_row(self._start_delay_slider, self._start_delay_value), 1, 1)

        advanced_capture_grid = QGridLayout()
        advanced_capture_grid.setHorizontalSpacing(8)
        advanced_capture_grid.setVerticalSpacing(7)
        advanced_capture_grid.addWidget(self._field_label("capture_backend"), 0, 0)
        advanced_capture_grid.addWidget(self._capture_backend_combo, 0, 1)
        advanced_capture_grid.addWidget(self._field_label("system_audio"), 1, 0)
        advanced_capture_grid.addWidget(self._capture_system_device_combo, 1, 1)
        advanced_capture_grid.addWidget(self._field_label("microphone"), 2, 0)
        advanced_capture_grid.addWidget(self._capture_microphone_device_combo, 2, 1)

        asr_grid = QGridLayout()
        asr_grid.setHorizontalSpacing(8)
        asr_grid.setVerticalSpacing(7)
        asr_grid.addWidget(self._field_label("asr_provider"), 0, 0)
        asr_grid.addWidget(self._asr_provider_combo, 0, 1)
        asr_grid.addWidget(self._field_label("asr_model"), 1, 0)
        asr_grid.addWidget(self._asr_model_combo, 1, 1)
        asr_grid.addWidget(self._field_label("asr_api_base"), 2, 0)
        asr_grid.addWidget(self._asr_api_base_edit, 2, 1)
        asr_grid.addWidget(self._field_label("asr_language_hints"), 3, 0)
        asr_grid.addWidget(self._asr_language_hints_edit, 3, 1)
        asr_grid.addWidget(self._field_label("asr_api_key"), 4, 0)
        asr_grid.addWidget(self._api_key_control(self._asr_api_key_edit, self._asr_api_key_status), 4, 1)
        asr_grid.addWidget(self._field_label("whisper_device"), 5, 0)
        asr_grid.addWidget(self._whisper_device_combo, 5, 1)
        asr_grid.addWidget(self._field_label("whisper_compute"), 6, 0)
        asr_grid.addWidget(self._whisper_compute_combo, 6, 1)
        asr_grid.addWidget(self._field_label("whisper_beam"), 7, 0)
        asr_grid.addWidget(self._slider_row(self._whisper_beam_slider, self._whisper_beam_value), 7, 1)
        asr_grid.addWidget(self._whisper_vad_check, 8, 0, 1, 2)
        asr_grid.addWidget(self._whisper_offline_check, 9, 0, 1, 2)
        add_provider_preview_row(asr_grid, self, "asr", 10)

        ocr_grid = QGridLayout()
        ocr_grid.setHorizontalSpacing(8)
        ocr_grid.setVerticalSpacing(7)
        ocr_grid.addWidget(self._field_label("ocr_provider"), 0, 0)
        ocr_grid.addWidget(self._ocr_provider_combo, 0, 1)
        ocr_grid.addWidget(self._field_label("ocr_model"), 1, 0)
        ocr_grid.addWidget(self._ocr_model_combo, 1, 1)
        ocr_grid.addWidget(self._field_label("ocr_api_base"), 2, 0)
        ocr_grid.addWidget(self._ocr_api_base_edit, 2, 1)
        ocr_grid.addWidget(self._field_label("ocr_api_key"), 3, 0)
        ocr_grid.addWidget(self._api_key_control(self._ocr_api_key_edit, self._ocr_api_key_status), 3, 1)
        ocr_grid.addWidget(self._field_label("ocr_api_region"), 4, 0)
        ocr_grid.addWidget(self._ocr_api_region_edit, 4, 1)
        ocr_grid.addWidget(self._field_label("ocr_timeout"), 5, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_timeout_slider, self._ocr_timeout_value), 5, 1)
        ocr_grid.addWidget(self._field_label("ocr_fps"), 6, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_fps_slider, self._ocr_fps_value), 6, 1)
        ocr_grid.addWidget(self._field_label("ocr_crop_top"), 7, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_crop_top_slider, self._ocr_crop_top_value), 7, 1)
        ocr_grid.addWidget(self._field_label("ocr_crop_height"), 8, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_crop_height_slider, self._ocr_crop_height_value), 8, 1)
        ocr_grid.addWidget(self._field_label("ocr_scale"), 9, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_scale_slider, self._ocr_scale_value), 9, 1)
        ocr_grid.addWidget(self._field_label("ocr_psm"), 10, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_psm_slider, self._ocr_psm_value), 10, 1)
        ocr_grid.addWidget(self._ocr_threshold_check, 11, 0, 1, 2)
        ocr_grid.addWidget(self._field_label("ocr_min_confidence"), 12, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_min_confidence_slider, self._ocr_min_confidence_value), 12, 1)
        ocr_grid.addWidget(self._field_label("ocr_merge_similarity"), 13, 0)
        ocr_grid.addWidget(self._slider_row(self._ocr_merge_similarity_slider, self._ocr_merge_similarity_value), 13, 1)
        add_provider_preview_row(ocr_grid, self, "ocr", 14)

        translation_grid = QGridLayout()
        translation_grid.setHorizontalSpacing(8)
        translation_grid.setVerticalSpacing(7)
        translation_grid.addWidget(self._field_label("translator"), 0, 0)
        translation_grid.addWidget(self._translator_combo, 0, 1)
        translation_grid.addWidget(self._field_label("translation_model"), 1, 0)
        translation_grid.addWidget(self._nllb_model_combo, 1, 1)
        translation_grid.addWidget(self._field_label("translator_device"), 2, 0)
        translation_grid.addWidget(self._translation_device_combo, 2, 1)
        translation_grid.addWidget(self._field_label("translator_api_base"), 3, 0)
        translation_grid.addWidget(self._translator_api_base_edit, 3, 1)
        translation_grid.addWidget(self._field_label("translator_api_key"), 4, 0)
        translation_grid.addWidget(
            self._api_key_control(self._translator_api_key_edit, self._translator_api_key_status), 4, 1
        )
        translation_grid.addWidget(self._field_label("translator_api_region"), 5, 0)
        translation_grid.addWidget(self._translator_api_region_edit, 5, 1)
        translation_grid.addWidget(self._field_label("translation_max_tokens"), 6, 0)
        translation_grid.addWidget(
            self._slider_row(self._translation_max_tokens_slider, self._translation_max_tokens_value), 6, 1
        )
        translation_grid.addWidget(self._field_label("translation_beams"), 7, 0)
        translation_grid.addWidget(
            self._slider_row(self._translation_beams_slider, self._translation_beams_value), 7, 1
        )
        translation_grid.addWidget(self._translation_offline_check, 8, 0, 1, 2)
        add_provider_preview_row(translation_grid, self, "translation", 9)

        tts_grid = QGridLayout()
        tts_grid.setHorizontalSpacing(8)
        tts_grid.setVerticalSpacing(7)
        tts_grid.addWidget(self._field_label("tts"), 0, 0)
        tts_grid.addWidget(self._tts_provider_combo, 0, 1)
        tts_grid.addWidget(self._tts_mode_label, 1, 0)
        tts_grid.addWidget(self._vieneu_mode_combo, 1, 1)
        tts_grid.addWidget(self._tts_model_label, 2, 0)
        tts_grid.addWidget(self._vieneu_model_combo, 2, 1)
        tts_grid.addWidget(self._field_label("vieneu_core"), 3, 0)
        tts_grid.addWidget(self._vieneu_core_combo, 3, 1)
        tts_grid.addWidget(self._field_label("vieneu_runtime"), 4, 0)
        tts_grid.addWidget(self._vieneu_runtime_combo, 4, 1)
        tts_grid.addWidget(self._field_label("vieneu_device"), 5, 0)
        tts_grid.addWidget(self._vieneu_device_combo, 5, 1)
        tts_grid.addWidget(self._field_label("vieneu_backend"), 6, 0)
        tts_grid.addWidget(self._vieneu_backend_combo, 6, 1)
        tts_grid.addWidget(self._field_label("vieneu_temperature"), 7, 0)
        tts_grid.addWidget(self._slider_row(self._vieneu_temperature_slider, self._vieneu_temperature_value), 7, 1)
        tts_grid.addWidget(self._field_label("tts_max_chars"), 8, 0)
        tts_grid.addWidget(self._slider_row(self._vieneu_max_chars_slider, self._vieneu_max_chars_value), 8, 1)
        tts_grid.addWidget(self._vieneu_offline_check, 9, 0, 1, 2)
        add_provider_preview_row(tts_grid, self, "tts", 10)

        tts_advanced_grid = QGridLayout()
        tts_advanced_grid.setHorizontalSpacing(8)
        tts_advanced_grid.setVerticalSpacing(7)
        tts_advanced_grid.addWidget(self._field_label("vieneu_path"), 0, 0)
        tts_advanced_grid.addWidget(self._vieneu_path_edit, 0, 1)
        tts_advanced_grid.addWidget(self._field_label("vieneu_python"), 1, 0)
        tts_advanced_grid.addWidget(self._vieneu_python_edit, 1, 1)
        tts_advanced_grid.addWidget(self._field_label("vieneu_decoder_path"), 2, 0)
        tts_advanced_grid.addWidget(self._vieneu_decoder_path_edit, 2, 1)
        tts_advanced_grid.addWidget(self._field_label("vieneu_encoder_path"), 3, 0)
        tts_advanced_grid.addWidget(self._vieneu_encoder_path_edit, 3, 1)
        tts_advanced_grid.addWidget(self._field_label("vieneu_standard_codec_path"), 4, 0)
        tts_advanced_grid.addWidget(self._vieneu_standard_codec_path_edit, 4, 1)
        tts_advanced_grid.addWidget(self._field_label("tts_api_base"), 5, 0)
        tts_advanced_grid.addWidget(self._tts_api_base_edit, 5, 1)
        tts_advanced_grid.addWidget(self._field_label("tts_api_key"), 6, 0)
        tts_advanced_grid.addWidget(self._api_key_control(self._tts_api_key_edit, self._tts_api_key_status), 6, 1)
        tts_advanced_grid.addWidget(self._field_label("tts_api_secret"), 7, 0)
        tts_advanced_grid.addWidget(
            self._api_key_control(self._tts_api_secret_edit, self._tts_api_secret_status), 7, 1
        )
        tts_advanced_grid.addWidget(self._field_label("tts_api_region"), 8, 0)
        tts_advanced_grid.addWidget(self._tts_api_region_edit, 8, 1)
        tts_advanced_grid.addWidget(self._field_label("tts_model"), 9, 0)
        tts_advanced_grid.addWidget(self._tts_model_edit, 9, 1)

        cleanup_grid = QGridLayout()
        cleanup_grid.setHorizontalSpacing(8)
        cleanup_grid.setVerticalSpacing(7)
        cleanup_grid.addWidget(self._field_label("transcript_cleanup"), 0, 0)
        cleanup_grid.addWidget(self._transcript_cleanup_mode_combo, 0, 1)
        cleanup_grid.addWidget(self._field_label("cleanup_provider"), 1, 0)
        cleanup_grid.addWidget(self._transcript_cleanup_provider_combo, 1, 1)
        cleanup_grid.addWidget(self._field_label("cleanup_model"), 2, 0)
        cleanup_grid.addWidget(self._transcript_cleanup_model_combo, 2, 1)
        cleanup_grid.addWidget(self._field_label("cleanup_api_base"), 3, 0)
        cleanup_grid.addWidget(self._transcript_cleanup_api_base_edit, 3, 1)
        cleanup_grid.addWidget(self._field_label("cleanup_api_key"), 4, 0)
        cleanup_grid.addWidget(
            self._api_key_control(
                self._transcript_cleanup_api_key_edit,
                self._transcript_cleanup_api_key_status,
            ),
            4,
            1,
        )
        cleanup_grid.addWidget(self._field_label("cleanup_timeout"), 5, 0)
        cleanup_grid.addWidget(self._slider_row(self._cleanup_timeout_slider, self._cleanup_timeout_value), 5, 1)
        add_provider_preview_row(cleanup_grid, self, "cleanup", 6)

        voice_ai_grid = QGridLayout()
        voice_ai_grid.setHorizontalSpacing(8)
        voice_ai_grid.setVerticalSpacing(7)
        voice_ai_grid.addWidget(self._field_label("speaker_gender_provider"), 0, 0)
        voice_ai_grid.addWidget(self._speaker_gender_provider_combo, 0, 1)
        voice_ai_grid.addWidget(self._field_label("speaker_gender_model"), 1, 0)
        voice_ai_grid.addWidget(self._speaker_gender_model_combo, 1, 1)
        voice_ai_grid.addWidget(self._field_label("speaker_gender_api_base"), 2, 0)
        voice_ai_grid.addWidget(self._speaker_gender_api_base_edit, 2, 1)
        voice_ai_grid.addWidget(self._field_label("speaker_gender_api_key"), 3, 0)
        voice_ai_grid.addWidget(
            self._api_key_control(self._speaker_gender_api_key_edit, self._speaker_gender_api_key_status), 3, 1
        )
        voice_ai_grid.addWidget(self._field_label("speaker_gender_timeout"), 4, 0)
        voice_ai_grid.addWidget(
            self._slider_row(self._speaker_gender_timeout_slider, self._speaker_gender_timeout_value),
            4,
            1,
        )
        voice_ai_grid.addWidget(self._field_label("source_filter_model"), 5, 0)
        voice_ai_grid.addWidget(self._source_filter_model_combo, 5, 1)
        add_provider_preview_row(voice_ai_grid, self, "speaker_gender", 6)

        self._transcript = QTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(True)
        self._transcript_view_combo = self._option_combo(
            _dropdown_options("transcript_views", self._config.gui_language), "all"
        )
        self._transcript_view_combo.setAccessibleName(self._tr("show_transcript"))
        self._transcript_view_combo.setToolTip(self._tr("show_transcript"))
        self._transcript_view_combo.currentIndexChanged.connect(self._render_transcript)
        self._transcript_type_combo = self._option_combo(
            _dropdown_options("transcript_types", self._config.gui_language), "all"
        )
        self._transcript_type_combo.setAccessibleName(self._tr("transcript_type"))
        self._transcript_type_combo.setToolTip(self._tr("transcript_type"))
        self._transcript_type_combo.currentIndexChanged.connect(self._render_transcript)
        self._export_transcript_button = self._make_button(
            "export_transcript",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        self._export_transcript_button.clicked.connect(self._export_transcript)
        self._transcript.setPlaceholderText(self._tr("transcript_placeholder"))

        basic_tab = build_basic_settings_tab(
            self,
            basic_source_grid=basic_source_grid,
            basic_voice_grid=basic_voice_grid,
            basic_playback_grid=basic_playback_grid,
            basic_processing_grid=basic_processing_grid,
        )
        models_tab = build_models_settings_tab(
            self,
            asr_grid=asr_grid,
            translation_grid=translation_grid,
            tts_grid=tts_grid,
            tts_advanced_grid=tts_advanced_grid,
            voice_ai_grid=voice_ai_grid,
            ocr_grid=ocr_grid,
            cleanup_grid=cleanup_grid,
        )
        advanced_tab = build_advanced_settings_tab(
            self,
            advanced_terms_grid=advanced_terms_grid,
            advanced_timing_grid=advanced_timing_grid,
            advanced_match_grid=advanced_match_grid,
            advanced_playback_grid=advanced_playback_grid,
            advanced_capture_grid=advanced_capture_grid,
        )
        readiness_tab = self._readiness_tab()
        task_center_tab = self._task_center_tab()
        transcript_tab = build_transcript_settings_tab(self)
        runtime_tab = self._runtime_tab()
        offline_models_tab = self._offline_models_tab()

        self._settings_tabs = build_settings_tabs(
            self,
            readiness_tab=readiness_tab,
            task_center_tab=task_center_tab,
            basic_tab=basic_tab,
            models_tab=models_tab,
            offline_models_tab=offline_models_tab,
            advanced_tab=advanced_tab,
            transcript_tab=transcript_tab,
            runtime_tab=runtime_tab,
        )
        settings_panel = build_settings_panel(self, self._settings_tabs)
        self._refresh_tts_options()
        self._sync_auto_voice_controls_enabled()
        self._sync_auto_match_controls_enabled()
        self._sync_asr_controls()
        self._sync_ocr_controls()
        self._sync_translation_model_combo_enabled()
        self._sync_source_filter_controls()
        self._sync_transcript_cleanup_controls()
        self._sync_vieneu_advanced_controls()
        self._refresh_preset_inspector()
        self._apply_control_tooltips()
        self._performance_preset_combo.currentIndexChanged.connect(self._apply_selected_performance_preset)
        self._connect_settings_autosave()
        self._connect_media_start_context_refresh()

        self._settings_scroll = settings_panel

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(video_panel)
        self._splitter.addWidget(self._settings_scroll)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes(list(DEFAULT_SIDEBAR_PANEL_SIZES))

        root = QVBoxLayout()
        self._root_layout = root
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)
        root.addWidget(source_bar)
        self._task_drawer = self._task_drawer_panel()
        root.addWidget(self._task_drawer)
        root.addWidget(self._splitter, 1)

        container = QWidget()
        container.setObjectName("root")
        container.setLayout(root)
        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar(self))
        self._media_stack.currentChanged.connect(lambda *_args: self._sync_media_browser_state())
        url_changed = getattr(self._video_placeholder, "urlChanged", None)
        if url_changed is not None:
            url_changed.connect(lambda *_args: self._sync_media_browser_state())
        self._sync_media_browser_state()
        self._sync_panel_visibility_buttons()
        self._sync_media_start_overlay()
        self._set_simple_sidebar_mode(True)
        if hasattr(self, "_refresh_next_action_panel"):
            self._refresh_next_action_panel()

    def _toggle_display_options(self, visible: bool) -> None:
        if hasattr(self, "_display_options_panel"):
            self._display_options_panel.setVisible(bool(visible))

    def _toggle_task_drawer(self) -> None:
        drawer = getattr(self, "_task_drawer", None)
        if drawer is None:
            self._select_settings_tab_for_widget(self._task_center_tab_widget)
            return
        self._task_drawer_user_open = not drawer.isVisible()
        drawer.setVisible(self._task_drawer_user_open)
        if drawer.isVisible() and hasattr(self, "_refresh_task_center"):
            self._refresh_task_center()

    def _task_drawer_panel(self) -> QFrame:
        drawer = QFrame()
        drawer.setObjectName("taskDrawer")
        drawer.hide()
        layout = QHBoxLayout(drawer)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self._task_drawer_state = QLabel(self._tr("task_drawer_state_idle"))
        self._task_drawer_state.setObjectName("taskDrawerState")
        self._task_drawer_state.setProperty("i18n_key", "task_drawer_state_idle")
        self._task_drawer_state.setMinimumWidth(88)
        layout.addWidget(self._task_drawer_state)
        self._task_drawer_summary = QLabel(self._tr("task_drawer_idle"))
        self._task_drawer_summary.setObjectName("taskDrawerSummary")
        self._task_drawer_summary.setProperty("i18n_key", "task_drawer_idle")
        self._task_drawer_summary.setWordWrap(True)
        self._task_drawer_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self._task_drawer_summary, 1)
        self._task_drawer_stop_button = self._make_button(
            "task_center_stop_all",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop),
        )
        self._task_drawer_stop_button.clicked.connect(self._stop_task_center_tasks)
        self._task_drawer_retry_button = self._make_button(
            "task_center_retry",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._task_drawer_retry_button.clicked.connect(self._retry_task_center_action)
        self._task_drawer_open_button = self._make_button(
            "task_drawer_open_center",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self._task_drawer_open_button.clicked.connect(self._open_task_center_from_drawer)
        layout.addWidget(self._task_drawer_stop_button)
        layout.addWidget(self._task_drawer_retry_button)
        layout.addWidget(self._task_drawer_open_button)
        return drawer

    def _open_task_center_from_drawer(self) -> None:
        if hasattr(self, "_task_drawer"):
            self._task_drawer.hide()
        self._task_drawer_user_open = False
        self._select_settings_tab_for_widget(self._task_center_tab_widget)

    def _show_command_palette(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr("command_palette_title"))
        layout = QVBoxLayout(dialog)
        prompt = QLabel(self._tr("command_palette_prompt"), dialog)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        actions = QListWidget(dialog)
        for key, action_id in (
            ("open_video", "open_video"),
            ("open_url", "open_url"),
            ("open_document", "open_document"),
            ("meeting_start_label", "meeting"),
            ("export_workflow_title", "export"),
            ("task_center_tab", "tasks"),
            ("models_tab", "models"),
            ("runtime_tab", "runtime"),
        ):
            item = QListWidgetItem(self._tr(key))
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
        self._run_command_palette_action(str(action_id or ""))

    def _run_command_palette_action(self, action_id: str) -> None:
        if action_id == "open_video":
            self._start_workflow("video", self._open_video)
        elif action_id == "open_url":
            self._start_workflow("url", self._open_video_url)
        elif action_id == "open_document":
            self._start_workflow("document", self._open_document)
        elif action_id == "meeting":
            self._start_workflow("meeting", self._toggle_meeting)
        elif action_id == "export":
            self._start_workflow("export", self._show_export_workflow)
        elif action_id == "tasks":
            self._select_settings_tab_for_widget(self._task_center_tab_widget)
        elif action_id == "models":
            self._select_settings_tab_for_widget(self._models_tab_widget)
        elif action_id == "runtime":
            self._select_settings_tab_for_widget(self._runtime_tab_widget)

    def _start_goal_workflow(self, workflow: str, action) -> None:
        selected_profile = str(getattr(self, "_readiness_selected_profile", "auto") or "auto")
        profile_key = (
            self._auto_goal_profile(str(workflow or "").strip().lower())
            if selected_profile == "auto"
            else selected_profile
        )
        if selected_profile == "auto" and profile_key:
            self._record_task_center_event(
                self._tr("first_run_profile_auto"),
                self._auto_goal_profile_reason(str(workflow or "").strip().lower(), profile_key),
            )
        if profile_key and hasattr(self, "_readiness_select_profile"):
            self._readiness_select_profile(profile_key)
            if hasattr(self, "_apply_readiness_profile"):
                self._apply_readiness_profile()
        self._start_workflow(workflow, action)

    def _auto_goal_profile(self, workflow: str) -> str:
        workflow_key = str(workflow or "").strip().lower()
        if workflow_key == "export":
            return "quality"
        if workflow_key in {"document", "meeting"}:
            return "meeting_document"
        if workflow_key in {"video", "url"} and self._offline_goal_ready():
            return "offline"
        return "quick"

    def _auto_goal_profile_reason(self, workflow: str, profile_key: str) -> str:
        profile_title_key = {
            "quick": "first_run_profile_quick",
            "offline": "first_run_profile_offline",
            "quality": "first_run_profile_quality",
            "meeting_document": "first_run_profile_meeting_document",
        }.get(profile_key, "first_run_profile_auto")
        reason_key = {
            "export": "auto_preset_reason_export",
            "document": "auto_preset_reason_document",
            "meeting": "auto_preset_reason_meeting",
            "url": "auto_preset_reason_url",
            "video": "auto_preset_reason_video",
        }.get(workflow, "auto_preset_reason_default")
        return self._tr("auto_preset_selected").format(
            profile=self._tr(profile_title_key),
            reason=self._tr(reason_key),
        )

    def _offline_goal_ready(self) -> bool:
        config = getattr(self, "_config", None)
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
            action = getattr(self, action_name, None)
            if action is not None:
                if action_name == "_workflow_health_action":
                    action.setText(self._workflow_health_action_label())
                else:
                    action.setText(self._tr(key))

    def _start_workflow(self, workflow: str, action) -> None:
        self._apply_workflow_sidebar_context(workflow)
        if callable(action):
            action()
        if hasattr(self, "_refresh_next_action_panel"):
            self._refresh_next_action_panel()

    def _apply_workflow_sidebar_context(self, workflow: str) -> None:
        tabs = getattr(self, "_settings_tabs", None)
        if tabs is None:
            return
        workflow_key = str(workflow or "").strip().lower()
        if getattr(self, "_simple_sidebar_enabled", True):
            contexts = {
                "video": ({2, 6, 3}, 2),
                "url": ({2, 6, 3}, 2),
                "document": ({2, 6, 3}, 2),
                "meeting": ({2, 6, 3}, 2),
                "export": ({2, 6, 3}, 2),
            }
        else:
            contexts = {
                "video": ({2, 3, 5, 6, 1}, 2),
                "url": ({2, 3, 5, 6, 1}, 2),
                "document": ({2, 6, 3, 5, 1}, 2),
                "meeting": ({2, 1, 6, 7}, 2),
                "export": ({2, 5, 6, 1}, 2),
            }
        visible_indexes, current_index = contexts.get(workflow_key, (set(range(tabs.count())), tabs.currentIndex()))
        self._set_sidebar_tab_visibility(visible_indexes)
        if hasattr(self, "_settings_scroll") and self._settings_scroll.isHidden():
            self._set_sidebar_panel_visible(True)
        if 0 <= current_index < tabs.count():
            tabs.setCurrentIndex(current_index)
        self._current_workflow_context = workflow_key
        title_key = {
            "video": "first_run_workflow_video",
            "url": "first_run_workflow_url",
            "document": "first_run_workflow_document",
            "meeting": "first_run_workflow_meeting",
            "export": "export_workflow_title",
        }.get(workflow_key, "settings_group_workflow")
        self.statusBar().showMessage(self._tr("status_workflow_context").format(workflow=self._tr(title_key)))

    def _set_simple_sidebar_mode(self, enabled: bool) -> None:
        self._simple_sidebar_enabled = bool(enabled)
        action = getattr(self, "_simple_sidebar_action", None)
        if action is not None and action.isChecked() != self._simple_sidebar_enabled:
            action.setChecked(self._simple_sidebar_enabled)
        tab_bar = getattr(self._settings_tabs, "tabBar", lambda: None)()
        if tab_bar is not None:
            tab_bar.setVisible(not self._simple_sidebar_enabled)
        workflow = str(getattr(self, "_current_workflow_context", "") or "")
        if workflow:
            self._apply_workflow_sidebar_context(workflow)
            return
        visible = {2, 3, 6} if self._simple_sidebar_enabled else set(range(self._settings_tabs.count()))
        self._set_sidebar_tab_visibility(visible)
        if self._settings_tabs.currentIndex() not in visible:
            self._settings_tabs.setCurrentIndex(2 if 2 in visible else 0)

    def _set_sidebar_tab_visibility(self, visible_indexes: set[int]) -> None:
        tabs = getattr(self, "_settings_tabs", None)
        if tabs is None:
            return
        set_visible = getattr(tabs, "setTabVisible", None)
        if callable(set_visible):
            for index in range(tabs.count()):
                set_visible(index, index in visible_indexes)
        self._sync_simple_sidebar_nav()

    def _sync_simple_sidebar_nav(self) -> None:
        buttons = getattr(self, "_settings_group_buttons", {})
        if not buttons:
            return
        simple = getattr(self, "_simple_sidebar_enabled", True)
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
            button = getattr(self, button_name, None)
            action = getattr(self, action_name, None)
            enabled = bool(button is None or button.isEnabled())
            any_enabled = any_enabled or enabled
            if action is not None:
                action.setEnabled(enabled)
        source_button = getattr(self, "_open_source_button", None)
        if source_button is not None:
            source_button.setEnabled(any_enabled)

    def _refresh_open_source_menu(self) -> None:
        action = getattr(self, "_open_clipboard_source_action", None)
        if action is None:
            return
        text = self._smart_source_clipboard_text()
        supported = self._smart_source_text_supported(text)
        action.setVisible(supported)
        action.setEnabled(supported)
        if supported:
            label = self._tr("smart_open_clipboard")
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
        self._preset_card_group = group
        presets = ("low_latency", "offline_lite", "balanced", "quality")
        for index, preset_id in enumerate(presets):
            button = QPushButton()
            button.setObjectName("presetCardButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(70)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setProperty("preset_id", preset_id)
            button.clicked.connect(lambda _checked=False, value=preset_id: self._select_preset_card(value))
            group.addButton(button)
            self._preset_cards[preset_id] = button
            layout.addWidget(button, index // 2, index % 2)
        self._refresh_preset_cards()
        return panel

    def _select_preset_card(self, preset_id: str) -> None:
        combo = getattr(self, "_performance_preset_combo", None)
        if combo is None:
            return
        self._set_combo_data(combo, preset_id)
        self._apply_selected_performance_preset()

    def _refresh_preset_cards(self) -> None:
        cards = getattr(self, "_preset_cards", {})
        if not cards:
            return
        current = ""
        combo = getattr(self, "_performance_preset_combo", None)
        if combo is not None:
            current = str(combo.currentData() or "")
        for preset_id, button in cards.items():
            label = self._preset_display_label(preset_id)
            detail = self._preset_card_detail(preset_id)
            button.setText(f"{label}\n{detail}" if detail else label)
            button.setChecked(preset_id == current)
            button.setToolTip(detail or label)

    def _preset_card_detail(self, preset_id: str) -> str:
        keys = {
            "low_latency": "preset_card_low_latency",
            "offline_lite": "preset_card_offline_lite",
            "balanced": "preset_card_balanced",
            "quality": "preset_card_quality",
        }
        key = keys.get(preset_id, "preset_card_default")
        return self._tr(key)

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
        self._media_start_workflow_buttons = {}
        self._media_start_workflow_cards = {}
        for index, (workflow_key, title_key, detail_key, icon_name, preset_id, callback) in enumerate(
            (
                (
                    "video",
                    "first_run_workflow_video",
                    "first_run_workflow_video_detail",
                    "video",
                    "low_latency",
                    self._open_video,
                ),
                (
                    "url",
                    "first_run_workflow_url",
                    "first_run_workflow_url_detail",
                    "url",
                    "online_lite",
                    self._open_video_url,
                ),
                (
                    "document",
                    "first_run_workflow_document",
                    "first_run_workflow_document_detail",
                    "document",
                    "offline_lite",
                    self._open_document,
                ),
                (
                    "meeting",
                    "first_run_workflow_meeting",
                    "first_run_workflow_meeting_detail",
                    "meeting",
                    "low_latency",
                    self._toggle_meeting,
                ),
            )
        ):
            card = self._media_start_workflow_card(
                workflow_key=workflow_key,
                title_key=title_key,
                detail_key=detail_key,
                icon_name=icon_name,
                preset_id=preset_id,
                callback=callback,
            )
            grid.addWidget(card, index // 2, index % 2)
            self._media_start_workflow_cards[workflow_key] = card
            self._media_start_workflow_buttons[title_key] = card._workflow_compat_button
        layout.addWidget(grid_host)

        layout.addWidget(self._media_start_quick_panel())

        setup_title = QPushButton(self._tr("first_run_profile_change"))
        setup_title.setObjectName("mediaStartSetupTitle")
        setup_title.setProperty("i18n_key", "first_run_profile_change")
        setup_title.setCheckable(True)
        setup_title.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        setup_title.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        layout.addWidget(setup_title)

        profile_row = QWidget()
        self._media_start_profile_row = profile_row
        profile_layout = QHBoxLayout(profile_row)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(8)
        self._media_start_profile_group = QButtonGroup(profile_row)
        self._media_start_profile_group.setExclusive(True)
        self._media_start_profile_buttons = {}
        for profile in READINESS_PROFILES:
            profile_key = str(profile["key"])
            button = QPushButton(self._tr(str(profile["title"])))
            button.setObjectName("mediaStartProfileButton")
            button.setCheckable(True)
            button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
            button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("launcher_profile", profile_key)
            button.setProperty("launcher_profile_title_key", str(profile["title"]))
            button.setProperty("launcher_profile_detail_key", str(profile["detail"]))
            button.clicked.connect(
                lambda _checked=False, key=profile_key: self._apply_media_start_profile(key)
            )
            self._media_start_profile_group.addButton(button)
            self._media_start_profile_buttons[profile_key] = button
            profile_layout.addWidget(button)
        profile_row.setVisible(False)
        setup_title.toggled.connect(profile_row.setVisible)
        layout.addWidget(profile_row)
        self._refresh_media_start_launcher_text()
        return panel

    def _media_start_quick_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("mediaStartQuickPanel")
        panel.setAcceptDrops(True)
        panel.installEventFilter(self)
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)

        drop_zone = QFrame()
        drop_zone.setObjectName("mediaStartDropZone")
        drop_zone.setAcceptDrops(True)
        drop_zone.installEventFilter(self)
        drop_layout = QVBoxLayout(drop_zone)
        drop_layout.setContentsMargins(12, 10, 12, 10)
        drop_layout.setSpacing(6)
        drop_title = QLabel(self._tr("media_start_drop_title"))
        drop_title.setObjectName("mediaStartDropTitle")
        drop_title.setProperty("i18n_key", "media_start_drop_title")
        drop_detail = QLabel(self._tr("media_start_drop_detail"))
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
        quick_edit.setPlaceholderText(self._tr("media_start_quick_placeholder"))
        quick_edit.setClearButtonEnabled(True)
        quick_edit.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        quick_edit.returnPressed.connect(self._media_start_submit_quick_source)
        quick_button = QPushButton(self._app_icon("open"), self._tr("media_start_quick_open"))
        quick_button.setObjectName("mediaStartQuickOpenButton")
        quick_button.setProperty("i18n_key", "media_start_quick_open")
        quick_button.setCursor(Qt.PointingHandCursor)
        quick_button.setFixedSize(self._COMMAND_BUTTON_WIDTH, self._COMMAND_BUTTON_HEIGHT)
        quick_button.clicked.connect(self._media_start_submit_quick_source)
        quick_layout.addWidget(quick_edit, 1)
        quick_layout.addWidget(quick_button)
        drop_layout.addWidget(quick_row)

        info_panel = QFrame()
        info_panel.setObjectName("mediaStartInfoPanel")
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(7)
        recent_title = QLabel(self._tr("media_start_recent_title"))
        recent_title.setObjectName("mediaStartSectionTitle")
        recent_title.setProperty("i18n_key", "media_start_recent_title")
        info_layout.addWidget(recent_title)
        self._media_start_recent_empty_label = QLabel(self._tr("media_start_recent_empty"))
        self._media_start_recent_empty_label.setObjectName("mediaStartMutedText")
        self._media_start_recent_empty_label.setProperty("i18n_key", "media_start_recent_empty")
        self._media_start_recent_empty_label.setWordWrap(True)
        info_layout.addWidget(self._media_start_recent_empty_label)
        self._media_start_recent_buttons = []
        for _index in range(3):
            button = QPushButton()
            button.setObjectName("mediaStartRecentButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(30)
            button.clicked.connect(
                lambda _checked=False, source_button=button: self._open_media_start_recent_source(
                    str(source_button.property("source") or "")
                )
            )
            button.hide()
            self._media_start_recent_buttons.append(button)
            info_layout.addWidget(button)

        config_title = QLabel(self._tr("media_start_config_title"))
        config_title.setObjectName("mediaStartSectionTitle")
        config_title.setProperty("i18n_key", "media_start_config_title")
        info_layout.addWidget(config_title)
        self._media_start_config_summary = QLabel()
        self._media_start_config_summary.setObjectName("mediaStartConfigSummary")
        self._media_start_config_summary.setWordWrap(True)
        info_layout.addWidget(self._media_start_config_summary)

        self._media_start_drop_zone = drop_zone
        self._media_start_quick_source_edit = quick_edit
        self._media_start_quick_open_button = quick_button
        layout.addWidget(drop_zone, 0, 0)
        layout.addWidget(info_panel, 0, 1)
        self._refresh_media_start_context()
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
        icon.setPixmap(self._app_icon(icon_name).pixmap(22, 22))
        header_layout.addWidget(icon)
        title = QLabel(self._tr(title_key))
        title.setObjectName("mediaStartWorkflowTitle")
        title.setProperty("i18n_key", title_key)
        title.setWordWrap(True)
        header_layout.addWidget(title, 1)
        body_layout.addWidget(header)

        detail = QLabel(self._tr(detail_key))
        detail.setObjectName("mediaStartWorkflowDetail")
        detail.setProperty("i18n_key", detail_key)
        detail.setWordWrap(True)
        body_layout.addWidget(detail)

        runtime = QLabel(self._workflow_runtime_status_text(workflow_key, preset_id))
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
        open_button = QPushButton(self._app_icon("open"), self._tr("workflow_card_open"))
        open_button.setObjectName("workflowCardPrimaryButton")
        open_button.setProperty("i18n_key", "workflow_card_open")
        open_button.setCursor(Qt.PointingHandCursor)
        open_button.setFixedHeight(self._COMMAND_BUTTON_HEIGHT)
        open_button.setFixedWidth(self._COMMAND_BUTTON_WIDTH)
        open_button.clicked.connect(
            lambda _checked=False, key=workflow_key, cb=callback: self._start_goal_workflow(key, cb)
        )
        compat_button = QPushButton(self._tr(title_key), card)
        compat_button.setObjectName("mediaStartWorkflowButton")
        compat_button.setProperty("i18n_key", title_key)
        compat_button.setToolTip(self._media_start_button_tooltip(title_key, detail_key))
        compat_button.clicked.connect(
            lambda _checked=False, key=workflow_key, cb=callback: self._start_goal_workflow(key, cb)
        )
        compat_button.hide()
        preset_button = QPushButton(self._tr("workflow_card_quick_preset"))
        preset_button.setObjectName("workflowCardSecondaryButton")
        preset_button.setProperty("i18n_key", "workflow_card_quick_preset")
        preset_button.setCursor(Qt.PointingHandCursor)
        preset_button.setToolTip(self._workflow_preset_tooltip(workflow_key, preset_id))
        preset_button.setFixedSize(self._COMMAND_BUTTON_WIDTH, self._COMMAND_BUTTON_HEIGHT)
        preset_button.clicked.connect(
            lambda _checked=False, key=workflow_key, preset=preset_id: self._apply_workflow_quick_preset(key, preset)
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
        preset_label = self._preset_display_label(preset_id)
        requirements = {
            "video": "workflow_badge_video",
            "url": "workflow_badge_url",
            "document": "workflow_badge_document",
            "meeting": "workflow_badge_meeting",
        }.get(workflow_key, "workflow_badge_default")
        return self._tr(requirements).format(preset=preset_label)

    def _workflow_preset_tooltip(self, workflow_key: str, preset_id: str) -> str:
        return self._tr("workflow_preset_tooltip").format(
            workflow=self._tr(f"workflow_name_{workflow_key}"),
            preset=self._preset_display_label(preset_id),
        )

    def _preset_display_label(self, preset_id: str) -> str:
        combo = getattr(self, "_performance_preset_combo", None)
        if combo is not None:
            index = combo.findData(preset_id)
            if index >= 0:
                return combo.itemText(index)
        for label, value in _dropdown_options("performance_presets", self._ui_language()):
            if value == preset_id:
                return _ui_label(label)
        return str(preset_id or "")

    def _apply_workflow_quick_preset(self, workflow_key: str, preset_id: str) -> None:
        combo = getattr(self, "_performance_preset_combo", None)
        if combo is not None:
            self._set_combo_data(combo, preset_id)
            self._apply_selected_performance_preset()
        self.statusBar().showMessage(
            self._tr("workflow_quick_preset_applied").format(
                workflow=self._tr(f"workflow_name_{workflow_key}"),
                preset=self._preset_display_label(preset_id),
            )
        )

    def _apply_media_start_profile(self, profile_key: str) -> None:
        if hasattr(self, "_readiness_select_profile"):
            self._readiness_select_profile(profile_key)
        else:
            self._readiness_selected_profile = profile_key
        if hasattr(self, "_apply_readiness_profile"):
            self._apply_readiness_profile()
        self._sync_media_start_profile_buttons()

    def _refresh_media_start_launcher_text(self) -> None:
        for card in getattr(self, "_media_start_workflow_cards", {}).values():
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
                title.setText(self._tr(title_key))
            if detail is not None and detail_key:
                detail.setText(self._tr(detail_key))
            if runtime is not None:
                runtime.setText(self._workflow_runtime_status_text(workflow_key, preset_id))
            if open_button is not None:
                open_button.setText(self._tr("workflow_card_open"))
            if compat_button is not None and title_key:
                compat_button.setText(self._tr(title_key))
                compat_button.setToolTip(self._media_start_button_tooltip(title_key, detail_key))
            if preset_button is not None:
                preset_button.setText(self._tr("workflow_card_quick_preset"))
                preset_button.setToolTip(self._workflow_preset_tooltip(workflow_key, preset_id))
        for button in getattr(self, "_media_start_profile_buttons", {}).values():
            title_key = str(button.property("launcher_profile_title_key") or "")
            detail_key = str(button.property("launcher_profile_detail_key") or "")
            if title_key and detail_key:
                button.setText(self._tr(title_key))
                button.setToolTip(self._media_start_button_tooltip(title_key, detail_key))
        self._sync_media_start_profile_buttons()
        self._refresh_media_start_context()

    def _connect_media_start_context_refresh(self) -> None:
        if getattr(self, "_media_start_context_refresh_connected", False):
            return
        self._media_start_context_refresh_connected = True
        widgets = (
            getattr(self, "_performance_preset_combo", None),
            getattr(self, "_asr_provider_combo", None),
            getattr(self, "_translator_combo", None),
            getattr(self, "_tts_provider_combo", None),
            getattr(self, "_audio_source_combo", None),
        )
        for widget in widgets:
            if widget is not None:
                widget.currentIndexChanged.connect(lambda *_args: self._refresh_media_start_context())
        self._refresh_media_start_context()

    def _refresh_media_start_context(self) -> None:
        edit = getattr(self, "_media_start_quick_source_edit", None)
        if edit is not None:
            edit.setPlaceholderText(self._tr("media_start_quick_placeholder"))
        recent_buttons = list(getattr(self, "_media_start_recent_buttons", []) or [])
        recent_urls = list(self._video_url_recent_urls_for_settings()[: len(recent_buttons)])
        empty_label = getattr(self, "_media_start_recent_empty_label", None)
        if empty_label is not None:
            empty_label.setText(self._tr("media_start_recent_empty"))
            empty_label.setVisible(not bool(recent_urls))
        for index, button in enumerate(recent_buttons):
            url = recent_urls[index] if index < len(recent_urls) else ""
            button.setProperty("source", url)
            if not url:
                button.hide()
                continue
            button.setText(self._media_start_recent_source_label(url))
            button.setToolTip(url)
            button.show()
        summary = getattr(self, "_media_start_config_summary", None)
        if summary is not None and hasattr(self, "_performance_preset_combo"):
            summary.setText(
                self._tr("media_start_config_summary").format(
                    profile=self._combo_text(self._performance_preset_combo),
                    asr=self._combo_text(self._asr_provider_combo),
                    translation=self._combo_text(self._translator_combo),
                    tts=self._combo_text(self._tts_provider_combo),
                )
            )

    @staticmethod
    def _media_start_recent_source_label(source: str) -> str:
        value = str(source or "").strip()
        parsed = urlparse(value)
        if parsed.netloc:
            label = f"{parsed.netloc}{parsed.path}"
        else:
            label = Path(value).name or value
        return label if len(label) <= 48 else f"...{label[-45:]}"

    def _media_start_button_tooltip(self, title_key: str, detail_key: str) -> str:
        return f"{self._tr(title_key)}\n{self._tr(detail_key)}"

    def _sync_media_start_profile_buttons(self) -> None:
        selected = str(getattr(self, "_readiness_selected_profile", "auto") or "auto")
        for profile_key, button in getattr(self, "_media_start_profile_buttons", {}).items():
            button.setChecked(profile_key == selected)

    def _sync_media_start_overlay(self) -> None:
        overlay = getattr(self, "_media_start_overlay", None)
        media_stack = getattr(self, "_media_stack", None)
        placeholder = getattr(self, "_video_placeholder", None)
        start_page = getattr(self, "_media_start_page", None)
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
            ("_vieneu_path_edit", "vieneu_path"),
            ("_vieneu_python_edit", "vieneu_python"),
            ("_vieneu_decoder_path_edit", "vieneu_decoder_path"),
            ("_vieneu_encoder_path_edit", "vieneu_encoder_path"),
            ("_vieneu_standard_codec_path_edit", "vieneu_standard_codec_path"),
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
            widget = getattr(self, widget_name, None)
            if widget is not None:
                self._set_control_tooltip(widget, key)

    def _set_preserve_terms_tooltip(self) -> None:
        if not hasattr(self, "_preserve_terms_check"):
            return
        tooltip = self._tr("preserved_terms_file_tooltip").format(path=self._config.preserved_source_terms_file)
        self._preserve_terms_check.setToolTip(tooltip)
        if hasattr(self, "_preserved_terms_file_edit"):
            self._preserved_terms_file_edit.setToolTip(tooltip)

    def _initial_capture_device_options(self) -> dict[str, list[str]]:
        return {
            "system": [self._config.capture_system_device] if self._config.capture_system_device else [],
            "microphone": [self._config.capture_microphone_device] if self._config.capture_microphone_device else [],
        }

    def _capture_devices_tab_changed(self, index: int) -> None:
        if not hasattr(self, "_advanced_tab_widget") or not hasattr(self, "_settings_tabs"):
            return
        if self._settings_tab_contains(self._settings_tabs.widget(index), self._advanced_tab_widget):
            self._load_capture_device_options()

    def _load_capture_device_options(self, *, force: bool = False) -> None:
        if getattr(self, "_capture_devices_loaded", False) and not force:
            return
        if not hasattr(self, "_capture_system_device_combo") or not hasattr(self, "_capture_microphone_device_combo"):
            return
        from ai_player.services.capture_sources import list_capture_device_options

        capture_devices = list_capture_device_options()
        self._replace_capture_device_options(self._capture_system_device_combo, capture_devices.get("system", []))
        self._replace_capture_device_options(
            self._capture_microphone_device_combo,
            capture_devices.get("microphone", []),
        )
        self._capture_devices_loaded = True

    def _replace_capture_device_options(self, combo: QComboBox, devices: list[str]) -> None:
        current = combo.currentData()
        was_blocked = combo.blockSignals(True)
        combo.clear()
        combo.addItem(self._i18n_text("auto"), "")
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
