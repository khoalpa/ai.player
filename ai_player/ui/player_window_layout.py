from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPalette, QShortcut, QTextDocument
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
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
    QTabWidget,
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
    available_asr_providers,
    available_gui_language_options,
    available_language_options,
    available_local_llm_options,
    available_ocr_models,
    available_ocr_providers,
    available_speaker_gender_models,
    available_translation_provider_options,
)
from ai_player.services.capture_sources import list_capture_device_options
from ai_player.services.source_voice_filter import (
    SOURCE_VOICE_FILTER_DEMUCS_MODELS,
    normalize_source_voice_filter_model,
)
from ai_player.services.speaker_voice_selector import normalize_speaker_gender_provider, normalize_voice_gender_mode
from ai_player.services.translation import normalize_translator_provider
from ai_player.services.tts import available_tts_providers, available_vieneu_modes, normalize_tts_provider
from ai_player.services.video_source import is_supported_browser_video_url
from ai_player.ui.player_window_media import DEFAULT_SIDEBAR_PANEL_SIZES, DEFAULT_SIDEBAR_PANEL_WIDTH
from ai_player.ui.player_window_utils import (
    dropdown_options as _dropdown_options,
)
from ai_player.ui.player_window_utils import (
    ui_label as _ui_label,
)

DEFAULT_MEDIA_HOME_URL = "https://www.google.com"
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
        self._open_file_button.clicked.connect(self._open_video)
        self._open_url_button = self._make_button(
            "open_url",
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._open_url_button.setObjectName("sourceButton")
        self._open_url_button.clicked.connect(self._open_video_url)
        self._open_document_button = self._make_button(
            "open_document",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
        )
        self._open_document_button.setObjectName("sourceButton")
        self._open_document_button.clicked.connect(self._open_document)
        self._meeting_button = self._make_button(
            "start",
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self._meeting_button.setObjectName("primaryButton")
        self._meeting_button.clicked.connect(self._toggle_meeting)
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
        self._export_button.clicked.connect(self._show_export_menu)
        self._video_fullscreen_button = self._icon_button(QStyle.StandardPixmap.SP_TitleBarMaxButton, "fullscreen")
        self._video_fullscreen_button.setToolTip(self._tr("fullscreen_tooltip"))
        self._video_fullscreen_button.setProperty("i18n_tooltip_key", "fullscreen_tooltip")
        self._video_fullscreen_button.clicked.connect(self._toggle_video_fullscreen)
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

        source_bar = QFrame()
        source_bar.setObjectName("sourceBar")
        self._source_bar = source_bar
        source_layout = QHBoxLayout(source_bar)
        source_layout.setContentsMargins(14, 9, 14, 9)
        source_layout.setSpacing(6)
        title = QLabel("AI Player")
        title.setObjectName("appTitle")
        source_layout.addWidget(title)
        source_layout.addWidget(self._source_label, 1)
        source_layout.addWidget(self._video_fullscreen_button)
        source_layout.addWidget(self._panel_toggle_button)
        source_layout.addWidget(self._panel_expand_button)
        source_layout.addWidget(self._panel_collapse_button)
        source_layout.addWidget(self._layout_reset_button)
        source_layout.addWidget(self._help_button)
        source_layout.addWidget(self._open_file_button)
        source_layout.addWidget(self._open_url_button)
        source_layout.addWidget(self._open_document_button)
        source_layout.addWidget(self._meeting_button)
        source_layout.addWidget(self._export_button)
        source_layout.addWidget(self._ui_language_combo)
        self._header_controls = (
            self._video_fullscreen_button,
            self._panel_expand_button,
            self._panel_collapse_button,
            self._layout_reset_button,
            self._help_button,
            self._open_file_button,
            self._open_url_button,
            self._open_document_button,
            self._meeting_button,
            self._export_button,
            self._ui_language_combo,
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
        self._telegram_channel_open_button.clicked.connect(self._open_selected_telegram_channel_item)
        self._telegram_channel_open_button.hide()
        self._telegram_channel_login_button = QPushButton(
            self._tr("telegram_channel_login"),
            self._telegram_channel_side_panel,
        )
        self._telegram_channel_login_button.setProperty("i18n_key", "telegram_channel_login")
        self._telegram_channel_login_button.clicked.connect(self._telegram_login_for_current_channel)
        self._telegram_channel_login_button.hide()
        self._telegram_channel_refresh_button = QPushButton(
            self._tr("telegram_channel_refresh"),
            self._telegram_channel_side_panel,
        )
        self._telegram_channel_refresh_button.setProperty("i18n_key", "telegram_channel_refresh")
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
        self._media_stack = QStackedWidget()
        self._media_stack.setObjectName("mediaStack")
        self._media_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._media_stack.addWidget(self._video_placeholder)
        self._media_stack.addWidget(self._video_widget)
        self._media_stack.addWidget(self._document_view)
        self._media_stack.addWidget(self._telegram_channel_view)
        self._media_stack.setCurrentWidget(self._video_placeholder)
        self._media_stack.installEventFilter(self)
        self._media_frame = QFrame()
        self._media_frame.setObjectName("mediaFrame")
        self._media_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._media_frame.installEventFilter(self)
        media_frame_layout = QVBoxLayout(self._media_frame)
        media_frame_layout.setContentsMargins(0, 0, 0, 0)
        media_frame_layout.addWidget(self._media_stack)
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
        self._media_home_button = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "")
        self._media_home_button.setObjectName("mediaHomeButton")
        self._media_home_button.setProperty("i18n_tooltip_key", "google_home_tooltip")
        self._media_home_button.setToolTip(self._tr("google_home_tooltip"))
        self._media_home_button.setFixedSize(32, 32)
        self._media_home_button.clicked.connect(self._open_media_home)
        self._telegram_browser_button = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "")
        self._telegram_browser_button.setObjectName("telegramBrowserButton")
        self._telegram_browser_button.setProperty("i18n_key", "telegram_channel_back")
        self._telegram_browser_button.setProperty("i18n_tooltip_key", "telegram_channel_back")
        self._telegram_browser_button.setToolTip(self._tr("telegram_channel_back"))
        self._telegram_browser_button.clicked.connect(self._return_to_telegram_channel_browser)
        self._telegram_browser_button.hide()
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

        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 1000)
        self._position_slider.sliderPressed.connect(self._begin_seek)
        self._position_slider.sliderReleased.connect(self._end_seek)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setMinimumWidth(104)

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
        playback_layout.setSpacing(3)
        playback_layout.addWidget(self._play_button)
        playback_layout.addWidget(self._pause_button)
        playback_layout.addWidget(self._stop_button)
        playback_layout.addWidget(self._previous_page_button)
        playback_layout.addWidget(self._next_page_button)
        playback_layout.addWidget(self._media_home_button)
        playback_layout.addWidget(self._telegram_browser_button)
        playback_layout.addSpacing(2)
        playback_layout.addWidget(self._aspect_combo)
        playback_layout.addWidget(self._playback_quality_combo)
        playback_layout.addWidget(self._subtitle_mode_combo)
        playback_layout.addWidget(self._subtitle_size_combo)
        playback_layout.addWidget(self._subtitle_color_combo)
        playback_layout.addWidget(self._subtitle_background_combo)
        playback_layout.addStretch(1)
        playback_layout.addWidget(self._audio_slider_control("dub_audio", self._dub_volume_slider))
        controls_layout.addLayout(timeline_layout)
        controls_layout.addLayout(playback_layout)

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

        self._asr_provider_combo = QComboBox()
        self._compact_combo(self._asr_provider_combo)
        for provider in available_asr_providers():
            self._asr_provider_combo.addItem(provider.name, provider.id)
        self._asr_provider_combo.setCurrentIndex(max(0, self._asr_provider_combo.findData(self._config.asr_provider)))
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
        self._asr_api_key_edit = QLineEdit(self._config.asr_api_key)
        self._asr_api_key_edit.setPlaceholderText(self._tr("asr_api_key_placeholder"))
        self._asr_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

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
        self._ocr_api_region_edit = QLineEdit(self._config.ocr_api_region)
        self._ocr_api_region_edit.setPlaceholderText(self._tr("ocr_api_region_placeholder"))

        self._translator_combo = QComboBox()
        self._compact_combo(self._translator_combo)
        for translator in available_translation_provider_options(self._config.gui_language):
            self._translator_combo.addItem(translator.name, translator.id)
        self._translator_combo.setCurrentIndex(
            max(0, self._translator_combo.findData(normalize_translator_provider(self._config.translator_provider)))
        )
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
        for provider in available_tts_providers():
            self._tts_provider_combo.addItem(provider.name, provider.id)
        self._tts_provider_combo.setCurrentIndex(
            max(0, self._tts_provider_combo.findData(normalize_tts_provider(self._config.tts_provider)))
        )
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
        self._tts_api_secret_edit = QLineEdit(self._config.tts_api_secret)
        self._tts_api_secret_edit.setPlaceholderText(self._tr("tts_api_secret_placeholder"))
        self._tts_api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._tts_api_region_edit = QLineEdit(self._config.tts_api_region)
        self._tts_api_region_edit.setPlaceholderText(self._tr("tts_api_region_placeholder"))
        self._tts_model_edit = QLineEdit(self._config.tts_model)
        self._tts_model_edit.setPlaceholderText(self._tr("tts_model_placeholder"))
        self._auto_voice_gender_check = QCheckBox(self._tr("auto_gender"))
        self._auto_voice_gender_check.setProperty("i18n_key", "auto_gender")
        self._auto_voice_gender_check.setChecked(self._config.dubbing_auto_voice_gender)
        self._auto_voice_gender_check.toggled.connect(self._sync_auto_voice_controls_enabled)
        self._auto_voice_gender_mode_combo = QComboBox()
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_stable"), "stable")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_balanced"), "balanced")
        self._auto_voice_gender_mode_combo.addItem(self._tr("voice_gender_mode_sensitive"), "sensitive")
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
        self._speaker_gender_provider_combo.addItem(
            self._tr("speaker_gender_provider_huggingface"), "huggingface_gender"
        )
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
        capture_devices = list_capture_device_options()
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

        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(8)
        preset_layout.addWidget(self._field_label("preset"))
        preset_layout.addWidget(self._performance_preset_combo, 1)

        basic_source_grid = QGridLayout()
        basic_source_grid.setHorizontalSpacing(8)
        basic_source_grid.setVerticalSpacing(7)
        basic_source_grid.addWidget(preset_row, 0, 0, 1, 2)
        basic_source_grid.addWidget(self._audio_source_panel(), 1, 0, 1, 2)
        basic_source_grid.addWidget(self._field_label("source_language"), 2, 0)
        basic_source_grid.addWidget(self._source_language_combo, 2, 1)
        basic_source_grid.addWidget(self._field_label("target_language"), 3, 0)
        basic_source_grid.addWidget(self._target_language_combo, 3, 1)

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
        asr_grid.addWidget(self._field_label("asr_api_key"), 3, 0)
        asr_grid.addWidget(self._asr_api_key_edit, 3, 1)
        asr_grid.addWidget(self._field_label("whisper_device"), 4, 0)
        asr_grid.addWidget(self._whisper_device_combo, 4, 1)
        asr_grid.addWidget(self._field_label("whisper_compute"), 5, 0)
        asr_grid.addWidget(self._whisper_compute_combo, 5, 1)
        asr_grid.addWidget(self._field_label("whisper_beam"), 6, 0)
        asr_grid.addWidget(self._slider_row(self._whisper_beam_slider, self._whisper_beam_value), 6, 1)
        asr_grid.addWidget(self._whisper_vad_check, 7, 0, 1, 2)
        asr_grid.addWidget(self._whisper_offline_check, 8, 0, 1, 2)

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
        ocr_grid.addWidget(self._ocr_api_key_edit, 3, 1)
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
        translation_grid.addWidget(self._translator_api_key_edit, 4, 1)
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
        tts_advanced_grid.addWidget(self._tts_api_key_edit, 6, 1)
        tts_advanced_grid.addWidget(self._field_label("tts_api_secret"), 7, 0)
        tts_advanced_grid.addWidget(self._tts_api_secret_edit, 7, 1)
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
        cleanup_grid.addWidget(self._transcript_cleanup_api_key_edit, 4, 1)
        cleanup_grid.addWidget(self._field_label("cleanup_timeout"), 5, 0)
        cleanup_grid.addWidget(self._slider_row(self._cleanup_timeout_slider, self._cleanup_timeout_value), 5, 1)

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
        voice_ai_grid.addWidget(self._speaker_gender_api_key_edit, 3, 1)
        voice_ai_grid.addWidget(self._field_label("speaker_gender_timeout"), 4, 0)
        voice_ai_grid.addWidget(
            self._slider_row(self._speaker_gender_timeout_slider, self._speaker_gender_timeout_value),
            4,
            1,
        )
        voice_ai_grid.addWidget(self._field_label("source_filter_model"), 5, 0)
        voice_ai_grid.addWidget(self._source_filter_model_combo, 5, 1)

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

        def scrollable_tab(content: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setObjectName("sideScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            return scroll

        settings_panel = QFrame()
        settings_panel.setObjectName("sidePanel")
        settings_panel.setMinimumWidth(DEFAULT_SIDEBAR_PANEL_WIDTH)
        settings_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(10)

        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(7, 7, 7, 7)
        basic_layout.setSpacing(10)
        basic_layout.addWidget(self._dub_button)
        basic_layout.addWidget(self._section_title("basic_source_group"))
        basic_layout.addLayout(basic_source_grid)
        basic_layout.addWidget(self._section_title("basic_voice_group"))
        basic_layout.addLayout(basic_voice_grid)
        basic_layout.addWidget(self._section_title("basic_playback_group"))
        basic_layout.addLayout(basic_playback_grid)
        basic_layout.addWidget(self._section_title("basic_processing_group"))
        basic_layout.addLayout(basic_processing_grid)
        basic_layout.addStretch(1)

        models_tab = QWidget()
        models_layout = QVBoxLayout(models_tab)
        models_layout.setContentsMargins(7, 7, 7, 7)
        models_layout.setSpacing(10)
        models_layout.addWidget(self._section_title("asr_group"))
        models_layout.addLayout(asr_grid)
        models_layout.addWidget(self._section_title("translation_group"))
        models_layout.addLayout(translation_grid)
        models_layout.addWidget(self._section_title("tts_group"))
        models_layout.addLayout(tts_grid)
        models_layout.addWidget(self._section_title("tts_advanced_group"))
        models_layout.addLayout(tts_advanced_grid)
        models_layout.addWidget(self._section_title("voice_ai_group"))
        models_layout.addLayout(voice_ai_grid)
        models_layout.addWidget(self._section_title("ocr_group"))
        models_layout.addLayout(ocr_grid)
        models_layout.addWidget(self._section_title("cleanup_group"))
        models_layout.addLayout(cleanup_grid)
        models_layout.addStretch(1)

        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(7, 7, 7, 7)
        advanced_layout.setSpacing(10)
        advanced_layout.addWidget(self._section_title("advanced_terms_group"))
        advanced_layout.addLayout(advanced_terms_grid)
        advanced_layout.addWidget(self._section_title("advanced_timing_group"))
        advanced_layout.addLayout(advanced_timing_grid)
        advanced_layout.addWidget(self._section_title("advanced_audio_match_group"))
        advanced_layout.addLayout(advanced_match_grid)
        advanced_layout.addWidget(self._section_title("advanced_playback_group"))
        advanced_layout.addLayout(advanced_playback_grid)
        advanced_layout.addWidget(self._section_title("advanced_capture_group"))
        advanced_layout.addLayout(advanced_capture_grid)
        advanced_layout.addStretch(1)

        transcript_tab = QWidget()
        transcript_layout = QVBoxLayout(transcript_tab)
        transcript_layout.setContentsMargins(7, 7, 7, 7)
        transcript_layout.setSpacing(7)
        transcript_toolbar = QWidget()
        transcript_toolbar_layout = QHBoxLayout(transcript_toolbar)
        transcript_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        transcript_toolbar_layout.setSpacing(6)
        transcript_toolbar_layout.addWidget(self._transcript_view_combo, 1)
        transcript_toolbar_layout.addWidget(self._transcript_type_combo, 1)
        transcript_toolbar_layout.addWidget(self._export_transcript_button)
        transcript_layout.addWidget(transcript_toolbar)
        transcript_layout.addWidget(self._transcript, 1)

        runtime_tab = self._runtime_tab()
        offline_models_tab = self._offline_models_tab()

        self._settings_tabs = QTabWidget()
        self._settings_tabs.setObjectName("settingsTabs")
        self._settings_tabs.addTab(scrollable_tab(basic_tab), self._tr("basic_tab"))
        self._settings_tabs.addTab(scrollable_tab(models_tab), self._tr("models_tab"))
        self._settings_tabs.addTab(scrollable_tab(offline_models_tab), self._tr("offline_models_tab"))
        self._settings_tabs.addTab(scrollable_tab(advanced_tab), self._tr("advanced_tab"))
        self._settings_tabs.addTab(transcript_tab, self._tr("transcript_tab"))
        self._settings_tabs.addTab(scrollable_tab(runtime_tab), self._tr("runtime_tab"))
        self._settings_tabs.currentChanged.connect(self._runtime_tab_changed)
        self._settings_tabs.currentChanged.connect(self._offline_models_tab_changed)
        settings_layout.addWidget(self._settings_tabs, 1)
        self._refresh_tts_options()
        self._sync_auto_voice_controls_enabled()
        self._sync_auto_match_controls_enabled()
        self._sync_asr_controls()
        self._sync_ocr_controls()
        self._sync_translation_model_combo_enabled()
        self._sync_source_filter_controls()
        self._sync_transcript_cleanup_controls()
        self._sync_vieneu_advanced_controls()
        self._apply_control_tooltips()
        self._performance_preset_combo.currentIndexChanged.connect(self._apply_selected_performance_preset)
        self._connect_settings_autosave()

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

    def _sync_media_browser_state(self) -> None:
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
        button.setVisible(
            media_stack.currentWidget() is placeholder and callable(getattr(placeholder, "setUrl", None))
        )

    def _sync_media_browser_address(self) -> None:
        media_stack = getattr(self, "_media_stack", None)
        placeholder = getattr(self, "_video_placeholder", None)
        source_label = getattr(self, "_source_label", None)
        if media_stack is None or placeholder is None or source_label is None:
            return
        if media_stack.currentWidget() is not placeholder:
            return
        url_getter = getattr(placeholder, "url", None)
        if not callable(url_getter):
            source_label.setText(self._tr("source_empty"))
            return
        url = url_getter().toString()
        source_label.setText(url or self._tr("source_empty"))

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
