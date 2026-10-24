from __future__ import annotations

from ai_player.ui.features import layout as layout_types


def build(context):
    context.layout._source_label = layout_types.QLabel(context.settings._tr("source_empty"))
    context.layout._source_label.setObjectName("sourceLabel")
    context.layout._source_label.setSizePolicy(layout_types.QSizePolicy.Ignored, layout_types.QSizePolicy.Preferred)
    context.layout._source_label.setTextInteractionFlags(layout_types.Qt.TextSelectableByMouse)

    context.layout._open_file_button = context.ui._make_button(
        "open_video",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DirOpenIcon),
    )
    context.layout._open_file_button.setObjectName("sourceButton")
    context.layout._open_file_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("video", context.sources._open_video)
    )
    context.ui._set_control_tooltip(context.layout._open_file_button, "open_video_tooltip")
    context.layout._open_url_button = context.ui._make_button(
        "open_url",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_BrowserReload),
    )
    context.layout._open_url_button.setObjectName("sourceButton")
    context.layout._open_url_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("url", context.sources._open_video_url)
    )
    context.layout._open_document_button = context.ui._make_button(
        "open_document",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_FileIcon),
    )
    context.layout._open_document_button.setObjectName("sourceButton")
    context.layout._open_document_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("document", context.sources._open_document)
    )

    context.layout._source_menu = layout_types.QMenu(context.window)
    context.layout._open_smart_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DirOpenIcon),
        context.settings._tr("smart_open_files"),
        context.window,
    )
    context.layout._open_smart_action.triggered.connect(context.sources._open_smart_source)
    context.layout._open_clipboard_source_action = layout_types.QAction(
        context.settings._tr("smart_open_clipboard"), context.window
    )
    context.layout._open_clipboard_source_action.triggered.connect(context.sources._open_smart_source_from_clipboard)
    context.layout._open_paste_source_action = layout_types.QAction(
        context.settings._tr("smart_open_paste"), context.window
    )
    context.layout._open_paste_source_action.triggered.connect(context.sources._open_smart_source_prompt)
    context.layout._open_video_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DirOpenIcon),
        context.settings._tr("open_video"),
        context.window,
    )
    context.layout._open_video_action.triggered.connect(
        lambda _checked=False: context.layout._start_workflow("video", context.sources._open_video)
    )
    context.layout._open_url_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_BrowserReload),
        context.settings._tr("open_url"),
        context.window,
    )
    context.layout._open_url_action.triggered.connect(
        lambda _checked=False: context.layout._start_workflow("url", context.sources._open_video_url)
    )
    context.layout._open_document_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_FileIcon),
        context.settings._tr("open_document"),
        context.window,
    )
    context.layout._open_document_action.triggered.connect(
        lambda _checked=False: context.layout._start_workflow("document", context.sources._open_document)
    )
    context.layout._source_menu.aboutToShow.connect(context.layout._refresh_open_source_menu)
    context.layout._source_menu.addAction(context.layout._open_smart_action)
    context.layout._source_menu.addAction(context.layout._open_clipboard_source_action)
    context.layout._source_menu.addAction(context.layout._open_paste_source_action)
    context.layout._open_source_button = context.ui._make_button(
        "open_source",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DirOpenIcon),
    )
    context.layout._open_source_button.setObjectName("sourceButton")
    context.layout._open_source_button.setToolTip(context.settings._tr("open_source_tooltip"))
    context.layout._open_source_button.setProperty("i18n_tooltip_key", "open_source_tooltip")
    context.layout._open_source_button.setMenu(context.layout._source_menu)

    context.layout._start_dubbing_button = context.ui._make_button(
        "start_dubbing",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_MediaPlay),
    )
    context.layout._start_dubbing_button.setObjectName("primaryButton")
    context.layout._start_dubbing_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("dubbing", context.dubbing._start_dubbing_from_header)
    )
    context.ui._set_control_tooltip(context.layout._start_dubbing_button, "start_dubbing_tooltip")
    context.layout._meeting_button = context.ui._make_button(
        "meeting_start_label",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_MediaPlay),
    )
    context.layout._meeting_button.setObjectName("primaryButton")
    context.layout._meeting_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("meeting", context.meeting._toggle_meeting)
    )
    context.layout._ui_language_combo = layout_types.QComboBox()
    context.ui._compact_combo(context.layout._ui_language_combo)
    context.layout._ui_language_combo.setMinimumContentsLength(10)
    for option in layout_types.available_gui_language_options():
        context.layout._ui_language_combo.addItem(layout_types._ui_label(option.name), option.id)
    context.layout._ui_language_combo.setCurrentIndex(
        max(0, context.layout._ui_language_combo.findData(context.config.gui_language))
    )
    context.layout._ui_language_combo.currentIndexChanged.connect(context.settings._gui_language_changed)
    context.layout._export_button = context.ui._make_button(
        "export",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DialogSaveButton),
    )
    context.layout._export_button.setObjectName("primaryButton")
    context.layout._export_button.clicked.connect(
        lambda _checked=False: context.layout._start_workflow("export", context.export._run_contextual_export)
    )
    context.layout._video_fullscreen_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_TitleBarMaxButton, "fullscreen"
    )
    context.layout._video_fullscreen_button.setToolTip(context.settings._tr("fullscreen_tooltip"))
    context.layout._video_fullscreen_button.setProperty("i18n_tooltip_key", "fullscreen_tooltip")
    context.layout._video_fullscreen_button.clicked.connect(context.media._toggle_video_fullscreen)
    context.layout._focus_media_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_TitleBarNormalButton, "focus_media"
    )
    context.layout._focus_media_button.setCheckable(True)
    context.layout._focus_media_button.setToolTip(context.settings._tr("focus_media_tooltip"))
    context.layout._focus_media_button.setProperty("i18n_tooltip_key", "focus_media_tooltip")
    context.layout._focus_media_button.clicked.connect(context.media._toggle_focus_media)
    context.layout._panel_toggle_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_TitleBarShadeButton, "panel_hide"
    )
    context.layout._panel_toggle_button.setToolTip(context.settings._tr("panel_toggle_tooltip"))
    context.layout._panel_toggle_button.setProperty("i18n_tooltip_key", "panel_toggle_tooltip")
    context.layout._panel_toggle_button.clicked.connect(context.media._toggle_sidebar_panel)
    context.layout._panel_expand_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_ArrowLeft, "sidebar_wider"
    )
    context.layout._panel_expand_button.setToolTip(context.settings._tr("sidebar_wider_tooltip"))
    context.layout._panel_expand_button.setProperty("i18n_tooltip_key", "sidebar_wider_tooltip")
    context.layout._panel_expand_button.clicked.connect(context.media._expand_sidebar_panel)
    context.layout._panel_collapse_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_ArrowRight, "sidebar_narrower"
    )
    context.layout._panel_collapse_button.setToolTip(context.settings._tr("sidebar_narrower_tooltip"))
    context.layout._panel_collapse_button.setProperty("i18n_tooltip_key", "sidebar_narrower_tooltip")
    context.layout._panel_collapse_button.clicked.connect(context.media._collapse_sidebar_panel)
    context.layout._layout_reset_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_DialogResetButton, "reset"
    )
    context.layout._layout_reset_button.setToolTip(context.settings._tr("reset_tooltip"))
    context.layout._layout_reset_button.setProperty("i18n_tooltip_key", "reset_tooltip")
    context.layout._layout_reset_button.clicked.connect(context.dubbing._reset_app)
    context.layout._help_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_DialogHelpButton, "help"
    )
    context.layout._help_button.setToolTip(context.settings._tr("help_tooltip"))
    context.layout._help_button.setProperty("i18n_tooltip_key", "help_tooltip")
    context.layout._help_button.clicked.connect(context.user_guide._show_user_guide)
    context.layout._top_panel_toggle_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_ArrowUp,
        "top_panel_hide_tooltip",
    )
    context.layout._top_panel_toggle_button.clicked.connect(context.media._toggle_top_panel)
    context.layout._bottom_panel_toggle_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_ArrowDown,
        "bottom_panel_hide_tooltip",
    )
    context.layout._bottom_panel_toggle_button.clicked.connect(context.media._toggle_bottom_panel)
    context.layout._right_panel_toggle_button = context.ui._icon_button(
        layout_types.QStyle.StandardPixmap.SP_ArrowRight,
        "right_panel_hide_tooltip",
    )
    context.layout._right_panel_toggle_button.clicked.connect(context.media._toggle_sidebar_panel)

    context.layout._simple_sidebar_enabled = True
    context.layout._tools_menu = layout_types.QMenu(context.window)
    context.layout._simple_sidebar_action = layout_types.QAction(
        context.settings._tr("simple_sidebar_mode"), context.window
    )
    context.layout._simple_sidebar_action.setCheckable(True)
    context.layout._simple_sidebar_action.setChecked(True)
    context.layout._simple_sidebar_action.toggled.connect(context.layout._set_simple_sidebar_mode)
    context.layout._task_center_action = layout_types.QAction(context.settings._tr("task_center_tab"), context.window)
    context.layout._task_center_action.triggered.connect(
        lambda: context.readiness._select_settings_tab_for_widget(context.task_center._task_center_tab_widget)
    )
    context.layout._offline_models_action = layout_types.QAction(
        context.settings._tr("offline_models_tab"), context.window
    )
    context.layout._offline_models_action.triggered.connect(
        lambda: context.readiness._select_settings_tab_for_widget(context.offline_models._offline_models_tab_widget)
    )
    context.layout._advanced_settings_action = layout_types.QAction(
        context.settings._tr("advanced_tab"), context.window
    )
    context.layout._advanced_settings_action.triggered.connect(
        lambda: context.readiness._select_settings_tab_for_widget(context.bindings._advanced_tab_widget)
    )
    context.layout._runtime_details_action = layout_types.QAction(context.settings._tr("runtime_tab"), context.window)
    context.layout._runtime_details_action.triggered.connect(
        lambda: context.readiness._select_settings_tab_for_widget(context.runtime._runtime_tab_widget)
    )
    context.layout._workflow_health_action = layout_types.QAction(
        context.settings._tr("workflow_health_title"), context.window
    )
    context.layout._workflow_health_action.triggered.connect(context.task_center._show_workflow_health)
    context.layout._adult_health_action = layout_types.QAction(
        context.settings._tr("adult_health_title"), context.window
    )
    context.layout._adult_health_action.triggered.connect(context.task_center._show_adult_extractor_health)
    context.layout._adult_hosts_action = layout_types.QAction(context.settings._tr("adult_hosts_title"), context.window)
    context.layout._adult_hosts_action.triggered.connect(context.task_center._show_adult_supported_hosts)
    context.layout._cache_inspector_action = layout_types.QAction(
        context.settings._tr("cache_inspector_title"), context.window
    )
    context.layout._cache_inspector_action.triggered.connect(context.task_center._show_cache_inspector)
    context.layout._clear_workflow_cache_action = layout_types.QAction(
        context.settings._tr("task_center_clear_cache"), context.window
    )
    context.layout._clear_workflow_cache_action.triggered.connect(context.task_center._clear_workflow_caches)
    context.layout._fullscreen_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_TitleBarMaxButton),
        context.settings._tr("fullscreen"),
        context.window,
    )
    context.layout._fullscreen_action.triggered.connect(context.media._toggle_video_fullscreen)
    context.layout._focus_media_action = layout_types.QAction(
        context.ui._app_icon("focus"),
        context.settings._tr("focus_media"),
        context.window,
    )
    context.layout._focus_media_action.setCheckable(True)
    context.layout._focus_media_action.triggered.connect(context.media._toggle_focus_media)
    context.layout._toggle_sidebar_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_TitleBarShadeButton),
        context.settings._tr("panel_hide"),
        context.window,
    )
    context.layout._toggle_sidebar_action.triggered.connect(context.media._toggle_sidebar_panel)
    context.layout._sidebar_wider_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_ArrowLeft),
        context.settings._tr("sidebar_wider"),
        context.window,
    )
    context.layout._sidebar_wider_action.triggered.connect(context.media._expand_sidebar_panel)
    context.layout._sidebar_narrower_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_ArrowRight),
        context.settings._tr("sidebar_narrower"),
        context.window,
    )
    context.layout._sidebar_narrower_action.triggered.connect(context.media._collapse_sidebar_panel)
    context.layout._reset_layout_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DialogResetButton),
        context.settings._tr("reset"),
        context.window,
    )
    context.layout._reset_layout_action.triggered.connect(context.dubbing._reset_app)
    context.layout._help_action = layout_types.QAction(
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_DialogHelpButton),
        context.settings._tr("help"),
        context.window,
    )
    context.layout._help_action.triggered.connect(context.user_guide._show_user_guide)
    context.layout._tools_menu.addAction(context.layout._simple_sidebar_action)
    context.layout._tools_menu.addSeparator()
    for action in (
        context.layout._task_center_action,
        context.layout._offline_models_action,
        context.layout._advanced_settings_action,
        context.layout._runtime_details_action,
        context.layout._workflow_health_action,
        context.layout._adult_health_action,
        context.layout._adult_hosts_action,
        context.layout._cache_inspector_action,
        context.layout._clear_workflow_cache_action,
    ):
        context.layout._tools_menu.addAction(action)
    context.layout._tools_menu.addSeparator()
    for action in (
        context.layout._fullscreen_action,
        context.layout._focus_media_action,
        context.layout._toggle_sidebar_action,
        context.layout._sidebar_wider_action,
        context.layout._sidebar_narrower_action,
        context.layout._reset_layout_action,
        context.layout._help_action,
    ):
        context.layout._tools_menu.addAction(action)
    context.layout._tools_menu_button = context.ui._make_button(
        "tools_menu",
        context.window.style().standardIcon(layout_types.QStyle.StandardPixmap.SP_FileDialogDetailedView),
    )
    context.layout._tools_menu_button.setObjectName("sourceButton")
    context.layout._tools_menu_button.setToolTip(context.settings._tr("tools_menu_tooltip"))
    context.layout._tools_menu_button.setProperty("i18n_tooltip_key", "tools_menu_tooltip")
    context.layout._tools_menu_button.setMenu(context.layout._tools_menu)
