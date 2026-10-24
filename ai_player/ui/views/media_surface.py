from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    source_bar = layout_types.QFrame()
    source_bar.setObjectName("sourceBar")
    context.layout._source_bar = source_bar
    source_layout = layout_types.QHBoxLayout(source_bar)
    source_layout.setContentsMargins(14, 9, 14, 9)
    source_layout.setSpacing(8)
    title = layout_types.QLabel("AI Player")
    title.setObjectName("appTitle")
    source_layout.addWidget(title)
    source_layout.addWidget(context.layout._source_label, 1)

    context.layout._task_status_button = layout_types.QPushButton(context.settings._tr("task_status_idle"))
    context.layout._task_status_button.setObjectName("taskStatusButton")
    context.layout._task_status_button.setFixedHeight(context.ui._COMMAND_BUTTON_HEIGHT)
    context.layout._task_status_button.setFixedWidth(context.ui._COMMAND_BUTTON_WIDTH)
    context.layout._task_status_button.setSizePolicy(layout_types.QSizePolicy.Fixed, layout_types.QSizePolicy.Fixed)
    context.layout._task_status_button.setCursor(layout_types.Qt.PointingHandCursor)
    context.layout._task_status_button.setToolTip(context.settings._tr("task_status_tooltip"))
    context.layout._task_status_button.clicked.connect(context.layout._toggle_task_drawer)
    source_layout.addWidget(context.layout._task_status_button)

    source_actions = layout_types.QFrame()
    source_actions.setObjectName("headerActionGroup")
    context.layout._header_action_group = source_actions
    source_actions_layout = layout_types.QHBoxLayout(source_actions)
    source_actions_layout.setContentsMargins(3, 3, 3, 3)
    source_actions_layout.setSpacing(3)
    source_actions_layout.addWidget(context.layout._open_source_button)
    source_layout.addWidget(source_actions)

    primary_actions = layout_types.QFrame()
    primary_actions.setObjectName("headerPrimaryGroup")
    context.layout._header_primary_group = primary_actions
    primary_actions_layout = layout_types.QHBoxLayout(primary_actions)
    primary_actions_layout.setContentsMargins(0, 0, 0, 0)
    primary_actions_layout.setSpacing(6)
    primary_actions_layout.addWidget(context.layout._start_dubbing_button)
    primary_actions_layout.addWidget(context.layout._meeting_button)
    primary_actions_layout.addWidget(context.layout._export_button)
    source_layout.addWidget(primary_actions)

    tools = layout_types.QFrame()
    tools.setObjectName("headerToolGroup")
    context.layout._header_tool_group = tools
    tools_layout = layout_types.QHBoxLayout(tools)
    tools_layout.setContentsMargins(3, 3, 3, 3)
    tools_layout.setSpacing(2)
    tools_layout.addWidget(context.layout._tools_menu_button)
    source_layout.addWidget(tools)
    source_layout.addWidget(context.layout._ui_language_combo)
    context.layout._header_controls = (
        context.layout._open_source_button,
        context.layout._start_dubbing_button,
        context.layout._meeting_button,
        context.layout._export_button,
        context.layout._ui_language_combo,
        context.layout._task_status_button,
        context.layout._tools_menu_button,
        context.layout._header_action_group,
        context.layout._header_primary_group,
        context.layout._header_tool_group,
    )

    context.layout._video_widget = layout_types.QVideoWidget()
    context.layout._video_widget.setObjectName("videoSurface")
    context.layout._video_widget.setSizePolicy(layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding)
    context.layout._video_widget.setAspectRatioMode(layout_types.Qt.AspectRatioMode.KeepAspectRatio)
    video_palette = context.layout._video_widget.palette()
    video_palette.setColor(layout_types.QPalette.Window, layout_types.QColor("#ffffff"))
    video_palette.setColor(layout_types.QPalette.Base, layout_types.QColor("#ffffff"))
    context.layout._video_widget.setPalette(video_palette)
    context.layout._video_widget.setAttribute(layout_types.Qt.WA_TranslucentBackground, False)
    context.layout._video_widget.setAttribute(layout_types.Qt.WA_NoSystemBackground, False)
    context.layout._video_widget.setAutoFillBackground(True)
    context.layout._video_widget.installEventFilter(context.window)
    context.layout._telegram_video_widget = layout_types.QVideoWidget()
    context.layout._telegram_video_widget.setObjectName("telegramVideoSurface")
    context.layout._telegram_video_widget.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    context.layout._telegram_video_widget.setAspectRatioMode(layout_types.Qt.AspectRatioMode.KeepAspectRatio)
    context.layout._telegram_video_widget.setPalette(video_palette)
    context.layout._telegram_video_widget.setAttribute(layout_types.Qt.WA_TranslucentBackground, False)
    context.layout._telegram_video_widget.setAttribute(layout_types.Qt.WA_NoSystemBackground, False)
    context.layout._telegram_video_widget.setAutoFillBackground(True)
    context.layout._telegram_video_widget.installEventFilter(context.window)
    if layout_types.QWebEngineView is not None:
        if layout_types._InPlayerWebEngineView is not None:
            context.layout._video_placeholder = layout_types._InPlayerWebEngineView()
        else:
            context.layout._video_placeholder = layout_types.QWebEngineView()
        if layout_types._InPlayerWebEnginePage is not None:
            context.layout._video_placeholder.setPage(
                layout_types._InPlayerWebEnginePage(context.layout._video_placeholder)
            )
        context.layout._video_placeholder.setUrl(layout_types.QUrl(layout_types.DEFAULT_MEDIA_HOME_URL))
    else:
        context.layout._video_placeholder = layout_types.QFrame()
    context.layout._video_placeholder.setObjectName("videoPlaceholder")
    context.layout._video_placeholder.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    if hasattr(context.layout._video_placeholder, "setAutoFillBackground"):
        context.layout._video_placeholder.setAutoFillBackground(True)
    context.layout._video_placeholder.installEventFilter(context.window)
    context.layout._document_view = layout_types.QTextEdit()
    context.layout._document_view.setObjectName("documentView")
    context.layout._document_view.setReadOnly(True)
    context.layout._document_view.setFrameShape(layout_types.QFrame.Shape.NoFrame)
    context.layout._document_view.setHorizontalScrollBarPolicy(layout_types.Qt.ScrollBarAlwaysOff)
    context.layout._document_view.setVerticalScrollBarPolicy(layout_types.Qt.ScrollBarAlwaysOff)
    context.layout._document_view.installEventFilter(context.window)
    context.layout._document_view.document().setDocumentMargin(0)
    context.layout._document_view.setPlaceholderText(context.settings._tr("document_placeholder"))
    context.layout._telegram_channel_view = layout_types.QFrame()
    context.layout._telegram_channel_view.setObjectName("telegramChannelView")
    context.layout._telegram_channel_view.setSizePolicy(
        layout_types.QSizePolicy.Expanding, layout_types.QSizePolicy.Expanding
    )
    context.layout._telegram_channel_view.installEventFilter(context.window)
    telegram_layout = layout_types.QVBoxLayout(context.layout._telegram_channel_view)
    telegram_layout.setContentsMargins(0, 0, 0, 0)
    telegram_layout.setSpacing(0)
    context.layout._telegram_channel_title = layout_types.QLabel(context.settings._tr("telegram_channel_browser_title"))
    context.layout._telegram_channel_title.setObjectName("telegramChannelTitle")
    context.layout._telegram_channel_title.setWordWrap(True)
    context.layout._telegram_channel_title.hide()
    context.layout._telegram_channel_status = layout_types.QLabel("")
    context.layout._telegram_channel_status.setObjectName("telegramChannelStatus")
    context.layout._telegram_channel_status.setWordWrap(True)
    context.layout._telegram_channel_status.hide()
    telegram_tools = layout_types.QHBoxLayout()
    telegram_tools.setContentsMargins(0, 0, 0, 0)
    telegram_tools.setSpacing(8)
    context.layout._telegram_channel_search = layout_types.QLineEdit()
    context.layout._telegram_channel_search.setObjectName("telegramChannelSearch")
    context.layout._telegram_channel_search.setFixedHeight(36)
    context.layout._telegram_channel_search.setMinimumWidth(0)
    context.layout._telegram_channel_search.setPlaceholderText(context.settings._tr("telegram_channel_search"))
    context.layout._telegram_channel_search.setProperty("i18n_key", "telegram_channel_search")
    context.layout._telegram_channel_search.textChanged.connect(context.sources._telegram_search_changed)
    context.layout._telegram_channel_search.returnPressed.connect(
        context.sources._search_current_telegram_channel_remote
    )
    context.layout._telegram_channel_remote_search_button = layout_types.QPushButton(
        context.settings._tr("telegram_channel_remote_search")
    )
    context.layout._telegram_channel_remote_search_button.setFixedSize(88, 36)
    context.layout._telegram_channel_remote_search_button.setProperty("i18n_key", "telegram_channel_remote_search")
    context.layout._telegram_channel_remote_search_button.clicked.connect(
        context.sources._search_current_telegram_channel_remote
    )
    context.layout._telegram_channel_filter_combo = layout_types.QComboBox()
    context.layout._telegram_channel_filter_combo.setObjectName("telegramChannelFilter")
    context.layout._telegram_channel_filter_combo.setFixedSize(96, 36)
    for value, key in (
        ("all", "telegram_filter_all"),
        ("video", "telegram_filter_video"),
        ("photo", "telegram_filter_photo"),
        ("document", "telegram_filter_document"),
        ("audio", "telegram_filter_audio"),
        ("text", "telegram_filter_text"),
        ("blacklist", "telegram_filter_blacklist"),
    ):
        context.layout._telegram_channel_filter_combo.addItem(context.settings._tr(key), value)
    return source_bar, telegram_layout, telegram_tools
