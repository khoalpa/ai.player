from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context, telegram_layout, telegram_tools):
    context.layout._telegram_channel_filter_combo.currentIndexChanged.connect(context.sources._telegram_filter_changed)
    context.layout._telegram_channel_load_more_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_load_more")
    )
    context.layout._telegram_channel_load_more_button.setFixedSize(96, 36)
    context.layout._telegram_channel_load_more_button.setCheckable(True)
    context.layout._telegram_channel_load_more_button.setProperty("i18n_key", "telegram_channel_load_more")
    context.layout._telegram_channel_load_more_button.toggled.connect(context.sources._telegram_load_more_toggled)
    context.layout._telegram_channel_translate_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_translate")
    )
    context.layout._telegram_channel_translate_button.setFixedSize(88, 36)
    context.layout._telegram_channel_translate_button.setCheckable(True)
    context.layout._telegram_channel_translate_button.setProperty("i18n_key", "telegram_channel_translate")
    context.layout._telegram_channel_translate_button.toggled.connect(context.sources._telegram_translation_toggled)
    context.layout._telegram_channel_auto_open_check = layout_types.QCheckBox(
        context.settings._tr("telegram_channel_auto_open")
    )
    context.layout._telegram_channel_auto_open_check.setObjectName("telegramChannelAutoOpen")
    context.layout._telegram_channel_auto_open_check.setFixedHeight(36)
    context.layout._telegram_channel_auto_open_check.setChecked(context.config.telegram_auto_open_videos)
    context.layout._telegram_channel_auto_open_check.setProperty("i18n_key", "telegram_channel_auto_open")
    telegram_tools.addWidget(context.layout._telegram_channel_search, 1)
    telegram_tools.addWidget(context.layout._telegram_channel_remote_search_button)
    telegram_tools.addWidget(context.layout._telegram_channel_filter_combo)
    telegram_tools.addWidget(context.layout._telegram_channel_load_more_button)
    telegram_tools.addWidget(context.layout._telegram_channel_translate_button)
    telegram_tools.addWidget(context.layout._telegram_channel_auto_open_check)
    context.layout._telegram_channel_list = layout_types.QListWidget()
    context.layout._telegram_channel_list.setObjectName("telegramChannelList")
    context.layout._telegram_channel_list.setAlternatingRowColors(True)
    context.layout._telegram_channel_list.setIconSize(layout_types.QSize(96, 96))
    context.layout._telegram_channel_list.setMinimumHeight(112)
    context.layout._telegram_channel_list.setTextElideMode(layout_types.Qt.TextElideMode.ElideNone)
    context.layout._telegram_channel_list.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    context.layout._telegram_channel_list.setWordWrap(True)
    context.layout._telegram_channel_list.setItemDelegate(
        layout_types.TelegramChannelItemDelegate(context.layout._telegram_channel_list)
    )
    context.layout._telegram_channel_list.installEventFilter(context.window)
    context.layout._telegram_channel_list.viewport().installEventFilter(context.window)
    context.layout._telegram_channel_list.currentItemChanged.connect(
        context.sources._telegram_channel_selection_changed
    )
    context.layout._telegram_channel_list.itemDoubleClicked.connect(context.sources._telegram_channel_item_activated)
    context.layout._telegram_channel_list.verticalScrollBar().valueChanged.connect(
        context.sources._telegram_channel_scroll_changed
    )
    context.layout._telegram_channel_preview = layout_types.QTextEdit()
    context.layout._telegram_channel_preview.setObjectName("telegramChannelPreview")
    context.layout._telegram_channel_preview.setReadOnly(True)
    context.layout._telegram_channel_preview.setMinimumHeight(160)
    context.layout._telegram_channel_preview.setMaximumHeight(240)
    context.layout._telegram_channel_preview.installEventFilter(context.window)
    context.layout._telegram_channel_thumbnail = layout_types.QLabel()
    context.layout._telegram_channel_thumbnail.setObjectName("telegramChannelThumbnail")
    context.layout._telegram_channel_thumbnail.setAlignment(layout_types.Qt.AlignCenter)
    context.layout._telegram_channel_thumbnail.setMinimumSize(320, 320)
    context.layout._telegram_channel_thumbnail.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    context.layout._telegram_channel_thumbnail.setScaledContents(False)
    context.layout._telegram_channel_thumbnail.installEventFilter(context.window)
    context.layout._telegram_channel_thumbnail.setText("")
    context.layout._telegram_channel_media_stack = layout_types.QStackedWidget()
    context.layout._telegram_channel_media_stack.setObjectName("telegramChannelMediaStack")
    context.layout._telegram_channel_media_stack.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    context.layout._telegram_channel_media_stack.addWidget(context.layout._telegram_channel_thumbnail)
    context.layout._telegram_channel_media_stack.addWidget(context.layout._telegram_video_widget)
    context.layout._telegram_channel_media_panel = layout_types.QFrame()
    context.layout._telegram_channel_media_panel.setObjectName("telegramChannelMediaPanel")
    context.layout._telegram_channel_media_panel.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    telegram_media_layout = layout_types.QGridLayout(context.layout._telegram_channel_media_panel)
    telegram_media_layout.setContentsMargins(12, 12, 12, 12)
    telegram_media_layout.setSpacing(0)
    telegram_media_layout.addWidget(context.layout._telegram_channel_media_stack, 0, 0)
    context.layout._telegram_channel_side_toggle_button = layout_types.QPushButton(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_ArrowRight),
        "",
    )
    context.layout._telegram_channel_side_toggle_button.setObjectName("telegramChannelSideToggle")
    context.layout._telegram_channel_side_toggle_button.setFixedSize(36, 36)
    context.layout._telegram_channel_side_toggle_button.setCheckable(True)
    context.layout._telegram_channel_side_toggle_button.setChecked(True)
    context.layout._telegram_channel_side_toggle_button.setCursor(layout_types.Qt.PointingHandCursor)
    context.layout._telegram_channel_side_toggle_button.toggled.connect(
        context.channel_browser._telegram_side_panel_toggled
    )
    telegram_media_layout.addWidget(
        context.layout._telegram_channel_side_toggle_button,
        0,
        0,
        layout_types.Qt.AlignmentFlag.AlignTop | layout_types.Qt.AlignmentFlag.AlignRight,
    )
    context.layout._telegram_channel_side_toggle_button.raise_()
    context.layout._telegram_channel_side_panel = layout_types.QWidget()
    context.layout._telegram_channel_side_panel.setObjectName("telegramChannelSidePanel")
    context.layout._telegram_channel_side_panel.setMinimumWidth(320)
    context.layout._telegram_channel_side_panel.setMaximumWidth(16777215)
    context.layout._telegram_channel_open_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_open_item"),
        context.layout._telegram_channel_side_panel,
    )
    context.layout._telegram_channel_open_button.setProperty("i18n_key", "telegram_channel_open_item")
    context.layout._telegram_channel_open_button.setFixedHeight(context.ui._COMMAND_BUTTON_HEIGHT)
    context.layout._telegram_channel_open_button.setFixedWidth(context.ui._COMMAND_BUTTON_WIDTH)
    context.layout._telegram_channel_open_button.clicked.connect(context.sources._open_selected_telegram_channel_item)
    context.layout._telegram_channel_open_button.hide()
    context.layout._telegram_channel_login_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_login"),
        context.layout._telegram_channel_side_panel,
    )
    context.layout._telegram_channel_login_button.setProperty("i18n_key", "telegram_channel_login")
    context.layout._telegram_channel_login_button.setFixedHeight(context.ui._COMMAND_BUTTON_HEIGHT)
    context.layout._telegram_channel_login_button.setFixedWidth(context.ui._COMMAND_BUTTON_WIDTH)
    context.layout._telegram_channel_login_button.clicked.connect(context.sources._telegram_login_for_current_channel)
    context.layout._telegram_channel_login_button.hide()
    context.layout._telegram_channel_refresh_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_refresh"),
        context.layout._telegram_channel_side_panel,
    )
    context.layout._telegram_channel_refresh_button.setProperty("i18n_key", "telegram_channel_refresh")
    context.layout._telegram_channel_refresh_button.setFixedHeight(context.ui._COMMAND_BUTTON_HEIGHT)
    context.layout._telegram_channel_refresh_button.setFixedWidth(context.ui._COMMAND_BUTTON_WIDTH)
    context.layout._telegram_channel_refresh_button.clicked.connect(context.sources._refresh_current_telegram_channel)
    context.layout._telegram_channel_refresh_button.hide()
    telegram_side_layout = layout_types.QVBoxLayout(context.layout._telegram_channel_side_panel)
    telegram_side_layout.setContentsMargins(12, 12, 12, 12)
    telegram_side_layout.setSpacing(8)
    telegram_side_layout.addLayout(telegram_tools)
    telegram_side_layout.addWidget(context.layout._telegram_channel_list, 1)
    telegram_side_layout.addWidget(context.layout._telegram_channel_preview)
    context.layout._telegram_channel_splitter = layout_types.QSplitter(layout_types.Qt.Horizontal)
    context.layout._telegram_channel_splitter.setObjectName("telegramChannelSplitter")
    context.layout._telegram_channel_splitter.addWidget(context.layout._telegram_channel_media_panel)
    context.layout._telegram_channel_splitter.addWidget(context.layout._telegram_channel_side_panel)
    context.layout._telegram_channel_splitter.setSizes([1, 1])
    context.layout._telegram_channel_splitter.setStretchFactor(0, 1)
    context.layout._telegram_channel_splitter.setStretchFactor(1, 1)
    context.layout._telegram_channel_splitter.setCollapsible(0, False)
    context.layout._telegram_channel_splitter.setCollapsible(1, False)
    context.layout._telegram_channel_splitter.splitterMoved.connect(
        context.channel_browser._telegram_side_panel_splitter_moved
    )
    telegram_layout.addWidget(context.layout._telegram_channel_splitter, 1)
    context.layout._aspect_combo = context.ui._option_combo(
        layout_types._dropdown_options("video_aspects", context.config.gui_language),
        layout_types.DEFAULT_MEDIA_ASPECT_RATIO,
    )
    context.layout._aspect_combo.setFixedWidth(80)
    context.layout._aspect_combo.currentIndexChanged.connect(context.sources._video_aspect_changed)
    context.layout._playback_quality_combo = context.ui._option_combo(
        layout_types._dropdown_options("playback_video_qualities", context.config.gui_language),
        context.config.playback_video_quality,
    )
    context.layout._playback_quality_combo.setFixedWidth(96)
    context.layout._playback_quality_combo.currentIndexChanged.connect(context.sources._playback_quality_changed)
    context.layout._video_url_full_cache_check = layout_types.QCheckBox(context.settings._tr("video_url_full_cache"))
    context.layout._video_url_full_cache_check.setProperty("i18n_key", "video_url_full_cache")
    context.layout._video_url_full_cache_check.setChecked(context.config.video_url_full_cache)
    context.layout._video_url_full_cache_check.setToolTip(context.settings._tr("video_url_full_cache_tooltip"))
    context.layout._video_url_full_cache_check.setProperty("i18n_tooltip_key", "video_url_full_cache_tooltip")
    context.layout._video_cache_dir_edit = layout_types.QLineEdit(context.config.video_cache_dir)
    context.layout._video_cache_dir_edit.setPlaceholderText(context.settings._tr("video_cache_dir_default"))
    context.layout._video_cache_dir_edit.setProperty("i18n_key", "video_cache_dir_default")
    context.layout._video_cache_dir_edit.editingFinished.connect(context.settings._queue_save_settings)
    context.layout._video_cache_dir_button = layout_types.QPushButton(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DirOpenIcon),
        "",
    )
    context.layout._video_cache_dir_button.setFixedSize(context.ui._ICON_BUTTON_SIZE, context.ui._ICON_BUTTON_SIZE)
    context.layout._video_cache_dir_button.setToolTip(context.settings._tr("video_cache_dir_choose"))
    context.layout._video_cache_dir_button.setProperty("i18n_tooltip_key", "video_cache_dir_choose")
    context.layout._video_cache_dir_button.clicked.connect(context.sources._choose_video_cache_dir)
    context.layout._video_cache_dir_reset_button = layout_types.QPushButton(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DialogResetButton),
        "",
    )
    context.layout._video_cache_dir_reset_button.setFixedSize(
        context.ui._ICON_BUTTON_SIZE, context.ui._ICON_BUTTON_SIZE
    )
    context.layout._video_cache_dir_reset_button.setToolTip(context.settings._tr("video_cache_dir_reset"))
    context.layout._video_cache_dir_reset_button.setProperty("i18n_tooltip_key", "video_cache_dir_reset")
    context.layout._video_cache_dir_reset_button.clicked.connect(context.sources._reset_video_cache_dir)
    context.layout._media_stack = layout_types.QStackedWidget()
    context.layout._media_stack.setObjectName("mediaStack")
    context.layout._media_stack.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding)
    context.layout._media_start_page = layout_types.QFrame()
    context.layout._media_start_page.setObjectName("mediaStartPage")
    context.layout._media_start_page.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    media_start_page_layout = layout_types.QGridLayout(context.layout._media_start_page)
    media_start_page_layout.setContentsMargins(0, 0, 0, 0)
    media_start_page_layout.setSpacing(0)
    context.layout._media_start_content = context.layout._media_start_panel()
    context.layout._media_start_overlay = layout_types.QScrollArea()
    context.layout._media_start_overlay.setObjectName("mediaStartScroll")
    context.layout._media_start_overlay.setWidgetResizable(True)
    context.layout._media_start_overlay.setFrameShape(layout_types.QFrame.Shape.NoFrame)
    context.layout._media_start_overlay.setHorizontalScrollBarPolicy(layout_types.Qt.ScrollBarAlwaysOff)
    context.layout._media_start_overlay.setVerticalScrollBarPolicy(layout_types.Qt.ScrollBarAsNeeded)
    context.layout._media_start_overlay.setWidget(context.layout._media_start_content)
    media_start_page_layout.addWidget(context.layout._media_start_overlay, 0, 0)
    context.layout._media_start_page.setAcceptDrops(True)
    context.layout._media_start_overlay.setAcceptDrops(True)
    context.layout._media_start_content.setAcceptDrops(True)
    context.layout._media_start_page.installEventFilter(context.window)
    context.layout._media_start_overlay.installEventFilter(context.window)
    context.layout._media_start_content.installEventFilter(context.window)
    context.layout._media_stack.addWidget(context.layout._media_start_page)
    context.layout._media_stack.addWidget(context.layout._video_placeholder)
    context.layout._media_stack.addWidget(context.layout._video_widget)
    context.layout._media_stack.addWidget(context.layout._document_view)
    context.layout._media_stack.addWidget(context.layout._telegram_channel_view)
    context.layout._media_stack.setCurrentWidget(context.layout._media_start_page)
    context.layout._media_stack.setAcceptDrops(True)
    context.layout._media_stack.installEventFilter(context.window)
    context.media.frame.frame = layout_types.QFrame()
    context.media.frame.frame.setObjectName("mediaFrame")
    context.media.frame.frame.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding)
    context.media.frame.frame.setAcceptDrops(True)
    context.media.frame.frame.installEventFilter(context.window)
    media_frame_layout = layout_types.QGridLayout(context.media.frame.frame)
    media_frame_layout.setContentsMargins(0, 0, 0, 0)
    media_frame_layout.setSpacing(0)
    media_frame_layout.addWidget(context.layout._media_stack, 0, 0)
    context.layout._subtitle_overlay = layout_types.SubtitleOverlayLabel()
    context.layout._subtitle_overlay.setWindowFlags(
        layout_types.Qt.Tool
        | layout_types.Qt.FramelessWindowHint
        | layout_types.Qt.NoDropShadowWindowHint
        | layout_types.Qt.BypassWindowManagerHint
        | layout_types.Qt.WindowDoesNotAcceptFocus
        | layout_types.Qt.WindowStaysOnTopHint
    )
    context.layout._subtitle_overlay.setObjectName("subtitleOverlay")
    context.layout._subtitle_overlay.setAlignment(layout_types.Qt.AlignCenter)
    context.layout._subtitle_overlay.setWordWrap(True)
    context.layout._subtitle_overlay.setTextFormat(layout_types.Qt.PlainText)
    context.layout._subtitle_overlay.setFrameStyle(layout_types.QFrame.NoFrame)
    context.layout._subtitle_overlay.setLineWidth(0)
    context.layout._subtitle_overlay.setMidLineWidth(0)
    context.layout._subtitle_overlay.setAttribute(layout_types.Qt.WA_TransparentForMouseEvents, True)
    context.layout._subtitle_overlay.setAttribute(layout_types.Qt.WA_ShowWithoutActivating, True)
    context.layout._subtitle_overlay.setAttribute(layout_types.Qt.WA_TranslucentBackground, True)
    context.layout._subtitle_overlay.setAttribute(layout_types.Qt.WA_NoSystemBackground, True)
    context.layout._subtitle_overlay.setAttribute(layout_types.Qt.WA_StyledBackground, False)
    context.layout._subtitle_overlay.setAutoFillBackground(False)
    context.layout._subtitle_overlay.hide()
    context.layout._fullscreen_shortcut = layout_types.QShortcut(layout_types.QKeySequence("F11"), context.window)
    context.layout._fullscreen_shortcut.setContext(layout_types.Qt.ApplicationShortcut)
    context.layout._fullscreen_shortcut.activated.connect(context.media._toggle_video_fullscreen)
