from __future__ import annotations

import html

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTabWidget, QTextBrowser, QVBoxLayout

from ai_player.core.config import AppConfig
from ai_player.services.translation import normalize_translator_provider
from ai_player.services.tts import normalize_tts_provider


class UserGuideMixin:
    def _show_user_guide(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._guide_text("title"))
        dialog.resize(860, 720)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        tabs = QTabWidget(dialog)
        tabs.setObjectName("userGuideTabs")
        for tab_title, tab_html in self._user_guide_tabs():
            browser = QTextBrowser(tabs)
            browser.setOpenExternalLinks(False)
            browser.setHtml(tab_html)
            tabs.addTab(browser, tab_title)
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _guide_language(self) -> str:
        return "en" if self._ui_language() == "en" else "vi"

    def _guide_text(self, key: str) -> str:
        return _GUIDE_TEXT[self._guide_language()].get(key, key)

    def _user_guide_tabs(self) -> list[tuple[str, str]]:
        return [
            (
                self._guide_text("tab_quick"),
                self._guide_html_page(self._quick_start_html(), include_intro=True),
            ),
            (
                self._guide_text("tab_sources"),
                self._guide_html_page(self._supported_sources_html()),
            ),
            (
                self._guide_text("tab_evaluation"),
                self._guide_html_page(self._settings_evaluation_html()),
            ),
            (
                self._guide_text("tab_reference"),
                self._guide_html_page(self._settings_reference_html()),
            ),
        ]

    def _user_guide_html(self) -> str:
        return self._guide_html_page(
            f"""
            {self._quick_start_html()}
            {self._supported_sources_html()}
            {self._settings_evaluation_html()}
            {self._settings_reference_html()}
            """,
            include_intro=True,
        )

    def _guide_html_page(self, body_html: str, *, include_intro: bool = False) -> str:
        intro_html = f'<p class="muted">{html.escape(self._guide_text("intro"))}</p>' if include_intro else ""
        return f"""
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Segoe UI, Arial, sans-serif; font-size: 13px; color: #172033; }}
            h1 {{ font-size: 24px; margin: 0 0 12px 0; }}
            h2 {{ font-size: 18px; margin: 22px 0 8px 0; color: #075985; }}
            h3 {{ font-size: 15px; margin: 16px 0 6px 0; }}
            ul {{ margin-top: 6px; }}
            li {{ margin-bottom: 5px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
            th, td {{ border: 1px solid #d7dde5; padding: 7px 8px; vertical-align: top; }}
            th {{ background: #eef6ff; text-align: left; }}
            .ok {{ color: #15803d; font-weight: 700; }}
            .warn {{ color: #b45309; font-weight: 700; }}
            .bad {{ color: #b91c1c; font-weight: 700; }}
            .muted {{ color: #607086; }}
            code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }}
        </style>
        </head>
        <body>
            <h1>{html.escape(self._guide_text("heading"))}</h1>
            {intro_html}
            {body_html}
        </body>
        </html>
        """

    def _quick_start_html(self) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        items = "".join(f"<li>{item}</li>" for item in text["quick_items"])
        slow_items = "".join(f"<li>{item}</li>" for item in text["slow_items"])
        return f"""
        <h2>{html.escape(text["quick_title"])}</h2>
        <ol>{items}</ol>
        <h2>{html.escape(text["slow_title"])}</h2>
        <ul>{slow_items}</ul>
        """

    def _supported_sources_html(self) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        video_items = "".join(f"<li>{item}</li>" for item in text["supported_video_items"])
        website_items = "".join(f"<li>{item}</li>" for item in text["supported_website_items"])
        document_items = "".join(f"<li>{item}</li>" for item in text["supported_document_items"])
        return f"""
        <h2>{html.escape(text["supported_title"])}</h2>
        <h3>{html.escape(text["supported_video_title"])}</h3>
        <ul>{video_items}</ul>
        <h3>{html.escape(text["supported_website_title"])}</h3>
        <ul>{website_items}</ul>
        <h3>{html.escape(text["supported_document_title"])}</h3>
        <ul>{document_items}</ul>
        """

    def _settings_evaluation_html(self) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        setting_tables = "\n".join(
            self._settings_group_table(title, rows) for title, rows in self._current_settings_groups()
        )
        finding_items = "\n".join(
            f"<li><span class='{level}'>{html.escape(label)}</span>: {html.escape(message)}</li>"
            for level, label, message in self._settings_findings()
        )
        return f"""
        <h2>{html.escape(text["evaluation_title"])}</h2>
        <p class="muted">{html.escape(text["current_setup_intro"])}</p>
        <ul>{finding_items}</ul>
        {setting_tables}
        """

    def _settings_group_table(self, title: str, rows: list[tuple[str, str, str]]) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        table_rows = "\n".join(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(value)}</td><td>{html.escape(note)}</td></tr>"
            for name, value, note in rows
        )
        return f"""
        <h3>{html.escape(title)}</h3>
        <table>
            <tr>
                <th>{html.escape(text["column_setting"])}</th>
                <th>{html.escape(text["column_current"])}</th>
                <th>{html.escape(text["column_description"])}</th>
            </tr>
            {table_rows}
        </table>
        """

    def _settings_reference_html(self) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        provider_model_tables = "\n".join(
            self._reference_option_table(title, rows) for title, rows in self._provider_model_reference_groups()
        )
        advanced_items = "".join(f"<li>{item}</li>" for item in text["advanced_items"])
        return f"""
        <h2>{html.escape(text["reference_title"])}</h2>
        <p class="muted">{html.escape(text["reference_intro"])}</p>
        {provider_model_tables}
        <h3>{html.escape(text["advanced_title"])}</h3>
        <ul>{advanced_items}</ul>
        """

    def _reference_option_table(self, title: str, rows: list[tuple[str, str, str, str]]) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        table_rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(kind)}</td>"
            f"<td><b>{html.escape(name)}</b></td>"
            f"<td>{html.escape(description)}</td>"
            f"<td>{html.escape(when)}</td>"
            "</tr>"
            for kind, name, description, when in rows
        )
        return f"""
        <h3>{html.escape(title)}</h3>
        <table>
            <tr>
                <th>{html.escape(text["column_kind"])}</th>
                <th>{html.escape(text["column_option"])}</th>
                <th>{html.escape(text["column_description"])}</th>
                <th>{html.escape(text["column_when"])}</th>
            </tr>
            {table_rows}
        </table>
        """

    def _provider_model_reference_groups(self) -> list[tuple[str, list[tuple[str, str, str, str]]]]:
        text = _GUIDE_TEXT[self._guide_language()]
        kind_provider = text["kind_provider"]
        kind_model = text["kind_model"]
        kind_mode = text["kind_mode"]
        kind_runtime = text["kind_runtime"]
        kind_backend = text["kind_backend"]
        return [
            (
                self._tr("asr_group"),
                self._option_reference_rows(self._asr_provider_combo, kind_provider, "asr_provider")
                + self._option_reference_rows(self._asr_model_combo, kind_model, "asr_model"),
            ),
            (
                self._tr("ocr_group"),
                self._option_reference_rows(self._ocr_provider_combo, kind_provider, "ocr_provider")
                + self._option_reference_rows(self._ocr_model_combo, kind_model, "ocr_model"),
            ),
            (
                self._tr("cleanup_group"),
                self._option_reference_rows(self._transcript_cleanup_provider_combo, kind_provider, "cleanup_provider")
                + self._option_reference_rows(self._transcript_cleanup_model_combo, kind_model, "cleanup_model"),
            ),
            (
                self._tr("translation_group"),
                self._option_reference_rows(self._translator_combo, kind_provider, "translator")
                + self._option_reference_rows(self._nllb_model_combo, kind_model, "translation_model"),
            ),
            (
                self._tr("tts_group"),
                self._option_reference_rows(self._tts_provider_combo, kind_provider, "tts")
                + self._option_reference_rows(self._vieneu_mode_combo, kind_mode, "vieneu_mode")
                + self._option_reference_rows(self._vieneu_model_combo, kind_model, "vieneu_model")
                + self._option_reference_rows(self._vieneu_runtime_combo, kind_runtime, "vieneu_runtime")
                + self._option_reference_rows(self._vieneu_backend_combo, kind_backend, "vieneu_backend"),
            ),
            (
                self._tr("source_filter"),
                self._option_reference_rows(self._source_filter_mode_combo, kind_provider, "source_filter_provider")
                + self._option_reference_rows(self._source_filter_model_combo, kind_model, "source_filter_model"),
            ),
        ]

    def _option_reference_rows(self, combo: QComboBox, kind: str, category: str) -> list[tuple[str, str, str, str]]:
        return [
            (
                kind,
                label,
                self._reference_note(category, value, label, "description"),
                self._reference_note(category, value, label, "when"),
            )
            for label, value in self._combo_items(combo)
        ]

    @staticmethod
    def _combo_items(combo: QComboBox) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for index in range(combo.count()):
            label = combo.itemText(index).strip()
            value = str(combo.itemData(index) or label).strip()
            key = (label, value)
            if label and key not in seen:
                items.append(key)
                seen.add(key)
        return items

    def _reference_note(self, category: str, value: str, label: str, field: str) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        notes = text["provider_model_notes"]
        category_notes = notes.get(category, {})
        note = category_notes.get(value) or category_notes.get(label)
        if note is None:
            lowered = f"{label} {value}".lower()
            for marker, marker_note in category_notes.items():
                if marker and marker.lower() in lowered:
                    note = marker_note
                    break
        if note is None:
            note = notes["fallback"].get(category, notes["fallback"]["default"])
        return note[field]

    def _current_settings_groups(self) -> list[tuple[str, list[tuple[str, str, str]]]]:
        config = self._current_runtime_config()
        notes = _GUIDE_TEXT[self._guide_language()]["setting_notes"]
        return [
            (
                self._tr("basic_source_group"),
                [
                    self._setting_row("language", self._combo_text(self._ui_language_combo), notes["language"]),
                    self._setting_row("preset", self._combo_text(self._performance_preset_combo), self._preset_note(config.performance_preset)),
                    self._setting_row("source", self._combo_text(self._audio_source_combo), self._source_note(config.audio_source)),
                    self._setting_row("transcript", self._path_or_empty(config.transcript_path), notes["transcript"]),
                    self._setting_row("source_language", self._combo_text(self._source_language_combo), notes["source_language"]),
                    self._setting_row("target_language", self._combo_text(self._target_language_combo), notes["target_language"]),
                ],
            ),
            (
                self._tr("basic_voice_group"),
                [
                    self._setting_row("voice_default", self._combo_text(self._tts_voice_combo), self._guide_text("voice_note")),
                    self._setting_row("auto_gender", self._bool_text(config.dubbing_auto_voice_gender), notes["auto_gender"]),
                    self._setting_row("voice_gender_mode", self._combo_text(self._auto_voice_gender_mode_combo), notes["voice_gender_mode"]),
                    self._setting_row("male_voice", self._combo_text(self._tts_male_voice_combo), notes["male_voice"]),
                    self._setting_row("female_voice", self._combo_text(self._tts_female_voice_combo), notes["female_voice"]),
                ],
            ),
            (
                self._tr("basic_playback_group"),
                [
                    self._setting_row("buffer", f"{int(config.dubbing_min_ready_ahead_seconds)} s", self._buffer_note(config.dubbing_min_ready_ahead_seconds)),
                    self._setting_row("speed", f"{config.dubbing_speed_percent:+d} %", self._guide_text("target_speed_note")),
                    self._setting_row("video_delay", f"{config.original_audio_playback_delay_seconds} s", notes["video_delay"]),
                    self._setting_row("original_audio", f"{config.original_audio_volume} %", notes["original_audio"]),
                    self._setting_row("dub_audio", f"{config.dubbing_voice_volume} %", notes["dub_audio"]),
                    self._setting_row("video_aspect_tooltip", self._combo_text(self._aspect_combo), notes["video_aspect"]),
                    self._setting_row("playback_quality_tooltip", self._combo_text(self._playback_quality_combo), notes["playback_quality"]),
                ],
            ),
            (
                self._tr("basic_processing_group"),
                [
                    self._setting_row("source_filter", self._bool_text(config.original_audio_voice_filter), notes["source_filter"]),
                    self._setting_row("source_filter_provider", self._combo_text(self._source_filter_mode_combo), notes["source_filter_provider"]),
                    self._setting_row("source_filter_model", self._combo_text(self._source_filter_model_combo), notes["source_filter_model"]),
                    self._setting_row("export_video_quality", self._combo_text(self._export_video_quality_combo), notes["export_video_quality"]),
                    self._setting_row("video_url_full_cache", self._bool_text(config.video_url_full_cache), notes["video_url_full_cache"]),
                ],
            ),
            (
                self._tr("asr_group"),
                [
                    self._setting_row("asr_provider", self._combo_text(self._asr_provider_combo), notes["asr_provider"]),
                    self._setting_row("asr_model", self._combo_text(self._asr_model_combo), self._guide_text("whisper_note")),
                    self._setting_row("whisper_device", self._combo_text(self._whisper_device_combo), notes["whisper_device"]),
                    self._setting_row("whisper_compute", self._combo_text(self._whisper_compute_combo), notes["whisper_compute"]),
                    self._setting_row("whisper_beam", str(config.whisper_beam_size), notes["whisper_beam"]),
                    self._setting_row("whisper_vad_filter", self._bool_text(config.whisper_vad_filter), notes["whisper_vad_filter"]),
                    self._setting_row("whisper_offline", self._bool_text(config.whisper_offline), notes["whisper_offline"]),
                ],
            ),
            (
                self._tr("ocr_group"),
                [
                    self._setting_row("ocr_provider", self._combo_text(self._ocr_provider_combo), notes["ocr_provider"]),
                    self._setting_row("ocr_model", self._combo_text(self._ocr_model_combo), notes["ocr_model"]),
                ],
            ),
            (
                self._tr("cleanup_group"),
                [
                    self._setting_row("transcript_cleanup", self._combo_text(self._transcript_cleanup_mode_combo), notes["transcript_cleanup"]),
                    self._setting_row("cleanup_provider", self._combo_text(self._transcript_cleanup_provider_combo), notes["cleanup_provider"]),
                    self._setting_row("cleanup_model", self._combo_text(self._transcript_cleanup_model_combo), notes["cleanup_model"]),
                    self._setting_row("cleanup_api_base", self._text_or_empty(config.transcript_cleanup_api_base), notes["cleanup_api_base"]),
                    self._setting_row("cleanup_api_key", self._masked_text(config.transcript_cleanup_api_key), notes["cleanup_api_key"]),
                ],
            ),
            (
                self._tr("translation_group"),
                [
                    self._setting_row("translator", self._combo_text(self._translator_combo), self._translator_note(config.translator_provider)),
                    self._setting_row("translation_model", self._combo_text(self._nllb_model_combo), self._guide_text("translation_model_note")),
                    self._setting_row("translator_device", self._combo_text(self._translation_device_combo), notes["translator_device"]),
                    self._setting_row("translation_max_tokens", str(config.translation_max_tokens), notes["translation_max_tokens"]),
                    self._setting_row("translation_beams", str(config.translation_num_beams), notes["translation_beams"]),
                    self._setting_row("translator_offline", self._bool_text(config.local_translation_offline), notes["translator_offline"]),
                ],
            ),
            (
                self._tr("tts_group"),
                [
                    self._setting_row("tts", self._combo_text(self._tts_provider_combo), self._tts_note(config)),
                    self._setting_row("mode", self._combo_text(self._vieneu_mode_combo), notes["mode"]),
                    self._setting_row("model", self._combo_text(self._vieneu_model_combo), notes["model"]),
                    self._setting_row("vieneu_runtime", self._combo_text(self._vieneu_runtime_combo), notes["vieneu_runtime"]),
                    self._setting_row("vieneu_device", self._combo_text(self._vieneu_device_combo), notes["vieneu_device"]),
                    self._setting_row("vieneu_backend", self._combo_text(self._vieneu_backend_combo), notes["vieneu_backend"]),
                    self._setting_row("vieneu_temperature", f"{config.vieneu_tts_temperature:.2f}", notes["vieneu_temperature"]),
                    self._setting_row("tts_max_chars", str(config.vieneu_tts_max_chars_chunk), self._guide_text("tts_chars_note")),
                    self._setting_row("vieneu_offline", self._bool_text(config.vieneu_tts_offline), notes["vieneu_offline"]),
                ],
            ),
            (
                self._tr("advanced_terms_group"),
                [
                    self._setting_row("keep_terms", self._bool_text(config.preserve_source_terms), notes["keep_terms"]),
                    (self._tr("preserved_terms"), self._path_or_empty(config.preserved_source_terms_file), notes["preserved_terms_file"]),
                ],
            ),
            (
                self._tr("advanced_timing_group"),
                [
                    self._setting_row("segment_length", f"{config.segment_seconds} s", notes["segment_length"]),
                    self._setting_row("prebuffer_segments", str(config.dubbing_prebuffer_segments), notes["prebuffer_segments"]),
                    self._setting_row("lookahead_segments", str(config.dubbing_lookahead_segments), notes["lookahead_segments"]),
                ],
            ),
            (
                self._tr("advanced_audio_match_group"),
                [
                    self._setting_row("auto_match", self._bool_text(config.dubbing_auto_match_audio), notes["auto_match"]),
                    self._setting_row("speed_min", f"{config.dubbing_speed_min:.2f}x", notes["speed_min"]),
                    self._setting_row("speed_max", f"{config.dubbing_speed_max:.2f}x", notes["speed_max"]),
                    self._setting_row("gain_min", f"{config.dubbing_volume_gain_min_db:+.0f} dB", notes["gain_min"]),
                    self._setting_row("gain_max", f"{config.dubbing_volume_gain_max_db:+.0f} dB", notes["gain_max"]),
                ],
            ),
            (
                self._tr("advanced_playback_group"),
                [
                    self._setting_row("overlap_policy", self._combo_text(self._overlap_policy_combo), notes["overlap_policy"]),
                    self._setting_row("start_delay", f"{config.dubbing_start_delay_seconds:.0f} s", notes["start_delay"]),
                ],
            ),
            (
                self._tr("advanced_capture_group"),
                [
                    self._setting_row("capture_backend", self._combo_text(self._capture_backend_combo), notes["capture_backend"]),
                    self._setting_row("system_audio", self._combo_text(self._capture_system_device_combo), notes["system_audio"]),
                    self._setting_row("microphone", self._combo_text(self._capture_microphone_device_combo), notes["microphone"]),
                ],
            ),
            (
                self._tr("transcript_tab"),
                [
                    self._setting_row("show_transcript", self._combo_text(self._transcript_view_combo), notes["show_transcript"]),
                    self._setting_row("transcript_type", self._combo_text(self._transcript_type_combo), notes["transcript_type"]),
                ],
            ),
        ]

    def _setting_row(self, label_key: str, value: str, note: str) -> tuple[str, str, str]:
        return self._tr(label_key), self._text_or_empty(value), note

    def _bool_text(self, value: bool) -> str:
        return self._guide_text("yes") if value else self._guide_text("no")

    def _text_or_empty(self, value: object) -> str:
        text = str(value or "").strip()
        return text or self._guide_text("empty_value")

    def _path_or_empty(self, value: object) -> str:
        return self._text_or_empty(value)

    def _masked_text(self, value: object) -> str:
        return self._guide_text("configured_secret") if str(value or "").strip() else self._guide_text("empty_value")

    def _settings_findings(self) -> list[tuple[str, str, str]]:
        config = self._current_runtime_config()
        text = _GUIDE_TEXT[self._guide_language()]
        findings: list[tuple[str, str, str]] = []
        tts_provider = normalize_tts_provider(config.tts_provider)
        translator_provider = normalize_translator_provider(config.translator_provider)
        if tts_provider == "vieneu" and config.vieneu_tts_device == "cpu":
            findings.append(("warn", text["label_slow"], text["finding_vieneu_cpu"]))
        if tts_provider == "edge":
            findings.append(("ok", text["label_good"], text["finding_edge"]))
        if translator_provider == "nllb_ct2":
            findings.append(("ok", text["label_good"], text["finding_ct2"]))
        if config.dubbing_min_ready_ahead_seconds >= 20:
            findings.append(("warn", text["label_wait"], text["finding_buffer"]))
        if config.audio_source == "document_editor":
            findings.append(("ok", text["label_editor"], text["finding_editor"]))
        if not findings:
            findings.append(("ok", text["label_ok"], text["finding_default"]))
        return findings

    @staticmethod
    def _combo_text(combo: QComboBox) -> str:
        return combo.currentText() or str(combo.currentData() or "")

    def _preset_note(self, value: str) -> str:
        return _GUIDE_TEXT[self._guide_language()]["preset_notes"].get(value, self._guide_text("preset_unknown_note"))

    def _source_note(self, value: str) -> str:
        return _GUIDE_TEXT[self._guide_language()]["source_notes"].get(value, self._guide_text("source_unknown_note"))

    def _translator_note(self, value: str) -> str:
        provider = normalize_translator_provider(value)
        return _GUIDE_TEXT[self._guide_language()]["translator_notes"].get(
            provider, self._guide_text("translator_default_note")
        )

    def _tts_note(self, config: AppConfig) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        provider = normalize_tts_provider(config.tts_provider)
        if provider == "edge":
            return text["tts_edge_note"]
        if config.vieneu_tts_device == "cpu":
            return text["tts_vieneu_cpu_note"]
        return text["tts_vieneu_note"]

    def _buffer_note(self, value: float) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        if value >= 20:
            return text["buffer_high_note"]
        if value <= 5:
            return text["buffer_low_note"]
        return text["buffer_balanced_note"]

    def _vieneu_note(self, config: AppConfig) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        if normalize_tts_provider(config.tts_provider) != "vieneu":
            return text["vieneu_not_used_note"]
        if config.vieneu_tts_mode == "turbo" and config.vieneu_tts_device == "cpu":
            return text["vieneu_turbo_cpu_note"]
        return text["vieneu_default_note"]


_GUIDE_TEXT = {
    "vi": {
        "title": "Hướng dẫn sử dụng",
        "heading": "Hướng dẫn sử dụng AI Player",
        "intro": "Trang này tóm tắt cách dùng nhanh và đánh giá các thiết lập đang chọn.",
        "tab_quick": "Quy trình",
        "tab_sources": "Nguồn hỗ trợ",
        "tab_evaluation": "Đang chọn",
        "tab_reference": "Tham chiếu",
        "quick_title": "Quy trình nhanh",
        "quick_items": [
            "Chọn <b>Preset</b> phù hợp với mục tiêu tốc độ, offline, GPU hoặc xuất bản.",
            "Chọn <b>Nguồn</b>: video gốc, transcript, subtitle, meeting hoặc editor tài liệu.",
            "Chọn ngôn ngữ nguồn/đích, máy dịch và TTS nếu cần tinh chỉnh.",
            "Bấm <b>Lồng tiếng / Đọc tài liệu</b>. Nút Play có thể tạm khóa đến khi đủ bộ đệm.",
            "Nếu phiên xử lý kéo dài bất thường, bấm <b>Đặt lại</b> để dừng và mở nguồn mới.",
        ],
        "slow_title": "Khi app bị chậm",
        "slow_items": [
            "Tránh mở nhiều cửa sổ AI Player cùng lúc vì mỗi cửa sổ có thể load model riêng.",
            "VieNeu local trên CPU có thể mất lâu ở đoạn đầu; dùng Edge TTS nếu ưu tiên tốc độ.",
            "Bộ đệm cao giúp phát ổn định hơn nhưng làm thời gian chờ ban đầu dài hơn.",
        ],
        "supported_title": "Nguồn và định dạng đã hỗ trợ",
        "supported_video_title": "Tệp video",
        "supported_website_title": "Trang web video",
        "supported_document_title": "Tệp tài liệu",
        "supported_video_items": [
            "Tệp video cục bộ: <code>.mp4</code>, <code>.mkv</code>, <code>.avi</code>, <code>.mov</code>, <code>.webm</code>.",
            "URL media trực tiếp: <code>.mp4</code>, <code>.mkv</code>, <code>.mov</code>, <code>.webm</code>, <code>.avi</code>, <code>.m4v</code>, <code>.m3u8</code>, <code>.mpd</code>.",
            "Giao thức URL hợp lệ: <code>http</code>, <code>https</code>, <code>rtsp</code>, <code>rtmp</code>, <code>mms</code>.",
        ],
        "supported_website_items": [
            "<b>Nền tảng video phổ biến</b>: YouTube (<code>youtube.com</code>, <code>m.youtube.com</code>, <code>music.youtube.com</code>, <code>youtu.be</code>), Vimeo (<code>vimeo.com</code>), Dailymotion (<code>dailymotion.com</code>, <code>dai.ly</code>).",
            "<b>Mạng xã hội và video ngắn</b>: TikTok (<code>tiktok.com</code>, <code>vm.tiktok.com</code>, <code>vt.tiktok.com</code>), Facebook (<code>facebook.com</code>, <code>m.facebook.com</code>, <code>web.facebook.com</code>, <code>fb.watch</code>), Instagram/Threads (<code>instagram.com</code>, <code>threads.net</code>), X/Twitter (<code>x.com</code>, <code>twitter.com</code>).",
            "<b>Cộng đồng và kênh chat</b>: Telegram (<code>t.me</code>, <code>telegram.me</code>).",
            "<b>Adult video</b>: <code>buomtv.*</code>, <code>*.buomtv.*</code>, <code>missav.ai</code>, <code>missav.com</code>, <code>missav.ws</code>, <code>supjav.com</code>, <code>javmost.com</code>, <code>javmost.cx</code>, <code>javgg.net</code>, <code>javgg.to</code>, <code>r18.com</code>, <code>javlibrary.com</code>, <code>javhd.com</code>.",
            "<b>Live/cam</b>: <code>chaturbate.com</code>, <code>chaturbate.eu</code>, <code>chaturbate.global</code>, <code>stripchat.com</code>, <code>bongacams*.com</code>, <code>bongacams*.net</code>, <code>livejasmin.com</code>, <code>cam4.com</code>, <code>camsoda.com</code>.",
        ],
        "supported_document_items": [
            "PowerPoint: <code>.pptx</code>.",
            "Word: <code>.docx</code>.",
            "PDF: <code>.pdf</code>.",
            "Text/Markdown/RTF: <code>.txt</code>, <code>.text</code>, <code>.md</code>, <code>.rtf</code>.",
            "Dữ liệu text: <code>.csv</code>, <code>.json</code>.",
            "Office cũ <code>.doc</code> và <code>.ppt</code> cần lưu lại thành <code>.docx</code> hoặc <code>.pptx</code> trước khi mở.",
        ],
        "evaluation_title": "Đánh giá cấu hình hiện tại",
        "reference_title": "Ý nghĩa các thiết lập chính",
        "translator_title": "Đánh giá từng máy dịch",
        "model_title": "Đánh giá model dịch",
        "advanced_title": "Nâng cao",
        "column_setting": "Thiết lập",
        "column_current": "Đang chọn",
        "column_note": "Đánh giá",
        "column_description": "Mô tả",
        "column_translator": "Máy dịch",
        "column_model": "Model",
        "column_strength": "Điểm mạnh",
        "column_risk": "Rủi ro / khi nào tránh",
        "column_recommendation": "Khuyến nghị",
        "column_tradeoff": "Đánh đổi",
        "column_when": "Nên dùng khi",
        "column_kind": "Loại",
        "column_option": "Provider / Model",
        "current_setup_intro": "Bảng dưới đây liệt kê chi tiết các thiết lập đang được chọn trên giao diện và tác dụng của từng thiết lập.",
        "reference_intro": "Các bảng dưới đây mô tả provider, model, mode, runtime và backend có trong giao diện. Danh sách model local có thể thay đổi theo thư mục model đã cài trên máy.",
        "kind_provider": "Provider",
        "kind_model": "Model",
        "kind_mode": "Mode",
        "kind_runtime": "Runtime",
        "kind_backend": "Backend",
        "yes": "Bật",
        "no": "Tắt",
        "empty_value": "Chưa chọn",
        "configured_secret": "Đã cấu hình",
        "setting_labels": {
            "preset": "Preset",
            "source": "Nguồn",
            "translator": "Máy dịch",
            "translation_model": "Model dịch",
            "tts": "TTS",
            "voice": "Giọng",
            "buffer": "Bộ đệm",
            "target_speed": "Tốc độ âm đích",
            "whisper": "Whisper",
            "vieneu": "VieNeu",
            "tts_chars": "Max ký tự TTS",
        },
        "setting_notes": {
            "language": "Ngôn ngữ hiển thị của toàn bộ giao diện và hướng dẫn.",
            "transcript": "File transcript dùng khi nguồn là Lời thoại hoặc khi cần lưu/đọc lời thoại có sẵn.",
            "source_language": "Ngôn ngữ của nội dung gốc; Auto để hệ thống tự nhận diện khi có thể.",
            "target_language": "Ngôn ngữ đầu ra cho bản dịch và giọng đích.",
            "auto_gender": "Tự chọn giọng nam/nữ dựa trên âm nguồn hoặc transcript khi có đủ thông tin.",
            "voice_gender_mode": "Cách hệ thống cân bằng giữa ổn định giọng và phản ứng nhanh khi đổi người nói.",
            "male_voice": "Giọng nam dùng khi chế độ tự chọn giới tính chọn nam.",
            "female_voice": "Giọng nữ dùng khi chế độ tự chọn giới tính chọn nữ.",
            "video_delay": "Trì hoãn video gốc để âm đích có thời gian chuẩn bị và phát khớp hơn.",
            "original_audio": "Âm lượng âm nguồn khi phát cùng âm đích.",
            "dub_audio": "Âm lượng giọng đích/lồng tiếng.",
            "video_aspect": "Tỷ lệ khung hình hiển thị cho vùng phát video.",
            "playback_quality": "Chất lượng khung hình khi mở video từ URL.",
            "source_filter": "Giảm giọng nói trong âm nguồn để nhường chỗ cho giọng đích.",
            "source_filter_provider": "Cách lọc giọng nguồn: nhanh nhẹ hoặc tách giọng bằng AI.",
            "source_filter_model": "Model dùng khi lọc giọng nguồn bằng AI.",
            "export_video_quality": "Preset chất lượng khi xuất video lồng tiếng hoặc video tài liệu.",
            "video_url_full_cache": "Tải video URL về cache trước khi phát để ổn định hơn, đổi lại chờ lâu hơn.",
            "asr_provider": "Backend nhận dạng giọng nói dùng cho nguồn cần nghe âm thanh.",
            "whisper_device": "Thiết bị chạy Whisper, ví dụ CPU, CUDA hoặc Auto.",
            "whisper_compute": "Kiểu tính toán của Whisper; int8 nhẹ hơn, float16 nhanh hơn trên GPU phù hợp.",
            "whisper_beam": "Số beam khi nhận dạng; cao hơn có thể chính xác hơn nhưng chậm hơn.",
            "whisper_vad_filter": "Bộ lọc đoạn có tiếng nói để giảm xử lý khoảng lặng.",
            "whisper_offline": "Chỉ dùng model Whisper đã có trên máy, không tải từ mạng.",
            "ocr_provider": "Backend OCR dùng khi đọc phụ đề cứng hoặc nội dung hình ảnh.",
            "ocr_model": "Thư mục/model OCR đang được dùng.",
            "transcript_cleanup": "Mức làm sạch lời thoại sau ASR/OCR trước khi dịch.",
            "cleanup_provider": "Backend làm sạch lời thoại: local, Ollama hoặc API tương thích OpenAI.",
            "cleanup_model": "Model dùng cho tác vụ làm sạch lời thoại.",
            "cleanup_api_base": "Endpoint API dùng khi provider làm sạch lời thoại cần server.",
            "cleanup_api_key": "Khóa API cho provider làm sạch lời thoại, nếu cần.",
            "translator_device": "Thiết bị chạy model dịch local.",
            "translation_max_tokens": "Giới hạn độ dài đầu ra mỗi lượt dịch.",
            "translation_beams": "Số beam khi dịch; cao hơn có thể ổn định hơn nhưng chậm hơn.",
            "translator_offline": "Chỉ dùng model dịch đã có trên máy, không tải từ mạng.",
            "mode": "Chế độ TTS VieNeu đang dùng.",
            "model": "Model TTS VieNeu đang được chọn.",
            "vieneu_runtime": "Cách chạy VieNeu TTS trong tiến trình hiện tại hoặc tiến trình phụ.",
            "vieneu_device": "Thiết bị chạy TTS local.",
            "vieneu_backend": "Backend tăng tốc cho TTS local nếu khả dụng.",
            "vieneu_temperature": "Độ biến thiên của giọng đọc; cao hơn có thể đa dạng hơn nhưng kém ổn định hơn.",
            "vieneu_offline": "Chỉ dùng tài nguyên TTS local đã có trên máy.",
            "keep_terms": "Giữ nguyên thuật ngữ ngôn ngữ nguồn theo file thuật ngữ.",
            "preserved_terms_file": "File danh sách thuật ngữ nguồn được giữ nguyên khi dịch.",
            "segment_length": "Độ dài mỗi đoạn xử lý ASR/OCR/TTS.",
            "prebuffer_segments": "Số đoạn cần chuẩn bị trước khi bắt đầu phát giọng đích.",
            "lookahead_segments": "Số đoạn nhìn trước để chuẩn bị giọng đích khi đang phát.",
            "auto_match": "Tự khớp tốc độ và âm lượng giọng đích với âm nguồn.",
            "speed_min": "Giới hạn tốc độ chậm nhất khi tự khớp âm thanh.",
            "speed_max": "Giới hạn tốc độ nhanh nhất khi tự khớp âm thanh.",
            "gain_min": "Mức giảm âm lượng tối đa khi tự cân âm.",
            "gain_max": "Mức tăng âm lượng tối đa khi tự cân âm.",
            "overlap_policy": "Cách xử lý khi giọng đích bị dài và có nguy cơ chồng lên đoạn sau.",
            "start_delay": "Độ trễ trước khi bắt đầu tạo/phát giọng đích.",
            "capture_backend": "Backend dùng để capture âm thanh hệ thống hoặc micro.",
            "system_audio": "Thiết bị âm thanh hệ thống được capture khi dùng nguồn live.",
            "microphone": "Micro được capture khi dùng nguồn meeting hoặc nguồn micro.",
            "show_transcript": "Phạm vi lời thoại hiển thị trong tab Lời thoại.",
            "transcript_type": "Loại lời thoại hiển thị: gốc, đã làm sạch hoặc bản dịch.",
        },
        "translation_model_note": "Danh sách thay đổi theo máy dịch đang chọn.",
        "voice_note": "Giọng dùng cho phát mặc định.",
        "target_speed_note": "Tăng nhẹ giúp khớp timeline; tăng quá cao có thể kém tự nhiên.",
        "whisper_note": "Chỉ ảnh hưởng khi nguồn cần nhận dạng âm thanh.",
        "tts_chars_note": "Giảm giá trị này nếu tạo giọng local bị lâu.",
        "preset_unknown_note": "Preset tùy chỉnh hoặc chưa xác định.",
        "source_unknown_note": "Nguồn chưa xác định.",
        "translator_default_note": "Có thể phù hợp tùy cặp ngôn ngữ và model đã cài.",
        "tts_edge_note": "Nhanh, nhẹ, nhưng cần Internet.",
        "tts_vieneu_cpu_note": "Offline/local nhưng nặng trên CPU.",
        "tts_vieneu_note": "Offline/local, tốt hơn nếu có GPU phù hợp.",
        "buffer_high_note": "Ổn định hơn nhưng bắt đầu chậm hơn.",
        "buffer_low_note": "Bắt đầu nhanh hơn nhưng dễ khựng.",
        "buffer_balanced_note": "Mức cân bằng cho phần lớn tác vụ.",
        "vieneu_not_used_note": "Không dùng khi TTS hiện tại là Edge.",
        "vieneu_turbo_cpu_note": "Turbo CPU vẫn có thể chậm khi đoạn dài hoặc máy đang tải nặng.",
        "vieneu_default_note": "Phù hợp khi cần giọng local/offline.",
        "label_slow": "Chậm",
        "label_good": "Tốt",
        "label_may_slow": "Có thể chậm",
        "label_wait": "Chờ lâu hơn",
        "label_editor": "Editor",
        "label_ok": "Ổn",
        "finding_vieneu_cpu": "VieNeu local trên CPU có thể mất lâu ở đoạn đầu, đặc biệt với Editor/Transcript.",
        "finding_edge": "Edge TTS thường phản hồi nhanh hơn và không load model local nặng.",
        "finding_ct2": "NLLB CTranslate2 là lựa chọn hợp lý cho tốc độ offline.",
        "finding_buffer": "Bộ đệm 20s trở lên ổn định hơn nhưng làm thời gian chờ ban đầu dài hơn.",
        "finding_editor": "Nguồn Editor phù hợp để đọc văn bản; ưu tiên Edge TTS nếu cần nhanh.",
        "finding_default": "Cấu hình hiện tại không có điểm rủi ro lớn.",
        "preset_notes": {
            "low_latency": "Xem nhanh với độ trễ thấp, ưu tiên phản hồi nhanh bằng Edge TTS.",
            "offline_lite": "Không cần Internet, nhẹ hơn cho CPU/máy yếu.",
            "balanced": "Cân bằng tốc độ và chất lượng.",
            "quality": "Ưu tiên chất lượng GPU và xuất bản chất lượng cao.",
        },
        "source_notes": {
            "original": "Lấy âm gốc từ video.",
            "system": "Capture âm hệ thống live.",
            "microphone": "Capture micro live.",
            "system_microphone": "Capture đồng thời âm hệ thống và micro live.",
            "transcript": "Đọc theo file transcript đã chọn.",
            "document_editor": "Đọc nội dung nhập hoặc dán trong Editor.",
            "subtitle": "OCR phụ đề cứng từ video.",
        },
        "translator_notes": {
            "nllb_ct2": "Khuyến nghị cho tốc độ offline.",
            "auto": "Tiện lợi nhưng có thể chậm do thử nhiều backend.",
            "none": "Không dịch, chỉ đọc văn bản nguồn.",
        },
        "provider_model_notes": {
            "fallback": {
                "default": {
                    "description": "Tùy chọn được phát hiện từ cấu hình hoặc thư mục local.",
                    "when": "Dùng khi tùy chọn này đã được cài và phù hợp với phần cứng hiện tại.",
                },
                "asr_model": {
                    "description": "Model Whisper/Faster-Whisper dùng để nhận dạng lời nói thành văn bản.",
                    "when": "Dùng khi nguồn cần nghe âm thanh, ví dụ video gốc, live hoặc meeting.",
                },
                "ocr_model": {
                    "description": "Model/thư mục tessdata dùng để nhận dạng chữ trong hình ảnh hoặc phụ đề cứng.",
                    "when": "Dùng khi nguồn là phụ đề cứng hoặc tài liệu/hình ảnh cần OCR.",
                },
                "cleanup_model": {
                    "description": "Model dùng để sửa lỗi ASR/OCR, bỏ lặp và làm câu lời thoại gọn hơn.",
                    "when": "Dùng khi transcript thô nhiễu, sai dấu câu hoặc có nhiều đoạn lặp.",
                },
                "translation_model": {
                    "description": "Model dịch dùng để chuyển văn bản nguồn sang ngôn ngữ đích.",
                    "when": "Dùng theo cặp ngôn ngữ, tốc độ mong muốn và model đã cài.",
                },
                "vieneu_model": {
                    "description": "Model VieNeu-TTS tạo giọng nói tiếng Việt/local.",
                    "when": "Dùng khi cần tạo giọng local/offline hoặc muốn kiểm soát runtime TTS.",
                },
                "source_filter_model": {
                    "description": "Model tách/lọc giọng nguồn để giảm lời thoại gốc.",
                    "when": "Dùng khi muốn giữ nhạc nền/âm môi trường nhưng giảm giọng nói nguồn.",
                },
            },
            "asr_provider": {
                "faster_whisper": {
                    "description": "Backend Faster-Whisper dùng CTranslate2 để nhận dạng giọng nói nhanh và nhẹ hơn Whisper gốc.",
                    "when": "Khuyến nghị mặc định cho video, live, meeting và transcript tạo từ âm thanh.",
                }
            },
            "asr_model": {
                "faster-whisper-base": {
                    "description": "Model Whisper base local, cân bằng giữa tốc độ, dung lượng và độ chính xác cơ bản.",
                    "when": "Phù hợp cho máy CPU/GPU phổ thông và nhu cầu nhận dạng nhanh.",
                },
                "base": {
                    "description": "Biến thể base của Whisper/Faster-Whisper, nhẹ và khởi động nhanh.",
                    "when": "Dùng khi ưu tiên tốc độ hoặc máy yếu.",
                },
            },
            "ocr_provider": {
                "tesseract": {
                    "description": "OCR truyền thống, chạy local, phụ thuộc tessdata cho từng ngôn ngữ.",
                    "when": "Dùng cho phụ đề cứng rõ nét hoặc tài liệu có chữ tương đối sạch.",
                }
            },
            "ocr_model": {
                "tessdata": {
                    "description": "Thư mục dữ liệu ngôn ngữ của Tesseract OCR.",
                    "when": "Cần có file ngôn ngữ tương ứng với phụ đề/tài liệu cần đọc.",
                }
            },
            "cleanup_provider": {
                "local": {
                    "description": "Chạy model làm sạch lời thoại ngay trên máy.",
                    "when": "Dùng khi muốn offline và đã có model local đủ nhẹ.",
                },
                "ollama": {
                    "description": "Gọi model qua Ollama local server.",
                    "when": "Dùng khi đã chạy Ollama và muốn đổi model linh hoạt.",
                },
                "openai": {
                    "description": "Gọi API tương thích OpenAI để làm sạch lời thoại.",
                    "when": "Dùng khi chấp nhận dùng API ngoài để có chất lượng sửa câu tốt hơn.",
                },
            },
            "cleanup_model": {
                "Qwen2.5": {
                    "description": "Model chat local phù hợp sửa câu, bỏ nhiễu nhẹ và giữ thuật ngữ.",
                    "when": "Dùng khi cần làm sạch lời thoại offline/local.",
                },
                "llama": {
                    "description": "Model qua Ollama/API, chất lượng phụ thuộc model đang được server cung cấp.",
                    "when": "Dùng khi model local mặc định chưa có hoặc muốn thử model khác.",
                },
            },
            "translator": {
                "nllb_ct2": {
                    "description": "NLLB chạy bằng CTranslate2, tối ưu tốc độ và bộ nhớ.",
                    "when": "Khuyến nghị mặc định cho dịch offline nhanh.",
                },
                "nllb": {
                    "description": "NLLB PyTorch/local, thường nặng hơn nhưng có thể hữu ích với một số model đầy đủ.",
                    "when": "Dùng khi ưu tiên chất lượng và máy đủ RAM/CPU/GPU.",
                },
                "none": {
                    "description": "Không dịch, giữ văn bản nguồn để đọc hoặc hiển thị.",
                    "when": "Dùng khi nội dung nguồn đã là ngôn ngữ mong muốn.",
                },
            },
            "translation_model": {
                "ct2": {
                    "description": "Model NLLB đã convert sang CTranslate2, chạy nhanh và tiết kiệm RAM hơn.",
                    "when": "Khuyến nghị cho CPU hoặc GPU phổ thông.",
                },
                "600M": {
                    "description": "NLLB distilled 600M, nhẹ hơn và tải nhanh hơn.",
                    "when": "Dùng khi cần phản hồi nhanh.",
                },
                "1.3B": {
                    "description": "NLLB 1.3B lớn hơn, có thể giữ nghĩa tốt hơn ở câu khó.",
                    "when": "Dùng khi ưu tiên chất lượng và chấp nhận chậm/nặng hơn.",
                },
                "none": {
                    "description": "Không cần model vì provider đang là Không dịch.",
                    "when": "Dùng cho nguồn đã phù hợp hoặc chỉ cần TTS.",
                },
            },
            "tts": {
                "vieneu": {
                    "description": "TTS local/offline cho giọng Việt, có thể chạy CPU/GPU tùy cấu hình.",
                    "when": "Dùng khi cần offline hoặc muốn giọng local ổn định.",
                },
                "edge": {
                    "description": "Microsoft Edge TTS online, nhẹ và phản hồi nhanh.",
                    "when": "Dùng khi có Internet và ưu tiên tốc độ.",
                },
                "none": {
                    "description": "Tắt TTS, không tạo audio mới.",
                    "when": "Dùng khi chỉ cần transcript/bản dịch hoặc kiểm thử pipeline.",
                },
            },
            "vieneu_mode": {
                "turbo": {
                    "description": "Chế độ VieNeu nhanh hơn, tối ưu cho phản hồi thấp.",
                    "when": "Dùng cho xem nhanh hoặc máy có GPU phù hợp.",
                },
                "standard": {
                    "description": "Chế độ VieNeu chuẩn, có thể nặng hơn nhưng ổn định với model chuẩn.",
                    "when": "Dùng khi cần giọng local và chấp nhận tốc độ chậm hơn.",
                },
            },
            "vieneu_model": {
                "Turbo": {
                    "description": "Model Turbo của VieNeu-TTS, ưu tiên tốc độ tạo giọng.",
                    "when": "Khuyến nghị cho phát gần thời gian thực.",
                },
                "Standard": {
                    "description": "Model Standard của VieNeu-TTS, thiên về chất lượng/ổn định.",
                    "when": "Dùng cho đọc tài liệu hoặc xuất bản khi không quá gấp.",
                },
            },
            "vieneu_runtime": {
                "subprocess": {
                    "description": "Chạy TTS trong tiến trình phụ để cô lập lỗi native/GPU.",
                    "when": "Khuyến nghị mặc định để app chính ổn định hơn.",
                },
                "inprocess": {
                    "description": "Chạy TTS trong tiến trình app chính, ít overhead hơn nhưng rủi ro crash cao hơn.",
                    "when": "Chỉ dùng khi môi trường TTS rất ổn định.",
                },
                "auto": {
                    "description": "Để app tự chọn runtime phù hợp.",
                    "when": "Dùng khi không chắc môi trường nào tốt nhất.",
                },
            },
            "vieneu_backend": {
                "auto": {
                    "description": "Tự chọn backend tăng tốc phù hợp với máy.",
                    "when": "Khuyến nghị cho đa số trường hợp.",
                },
                "native": {
                    "description": "Backend native/local cơ bản, ít phụ thuộc hơn.",
                    "when": "Dùng khi backend tăng tốc gặp lỗi.",
                },
                "lmdeploy": {
                    "description": "Backend tăng tốc LMDeploy cho môi trường tương thích.",
                    "when": "Dùng khi GPU/runtime hỗ trợ tốt và cần tốc độ.",
                },
            },
            "source_filter_provider": {
                "fast": {
                    "description": "Bộ lọc nhanh dựa trên tín hiệu/kênh, rất nhẹ.",
                    "when": "Dùng khi cần giảm giọng nhanh và chấp nhận chất lượng tách vừa phải.",
                },
                "ai": {
                    "description": "Tách giọng bằng Demucs/AI, nặng hơn nhưng sạch hơn.",
                    "when": "Dùng khi muốn giữ nhạc nền tốt hơn và máy đủ mạnh.",
                },
            },
            "source_filter_model": {
                "htdemucs": {
                    "description": "Model Demucs cân bằng, phổ biến cho tách nguồn âm thanh.",
                    "when": "Khuyến nghị mặc định cho lọc giọng bằng AI.",
                },
                "htdemucs_ft": {
                    "description": "Biến thể fine-tuned của htdemucs.",
                    "when": "Dùng khi muốn thử chất lượng tách khác với model mặc định.",
                },
                "htdemucs_6s": {
                    "description": "Biến thể Demucs tách nhiều stem hơn.",
                    "when": "Dùng khi cần tách nguồn chi tiết hơn và chấp nhận nặng hơn.",
                },
                "mdx_extra": {
                    "description": "Model MDX extra, có thể phù hợp một số loại nhạc/giọng.",
                    "when": "Dùng để thử nếu htdemucs chưa cho kết quả tốt.",
                },
            },
        },
        "translator_rows": [
            (
                "NLLB CTranslate2",
                "Nhanh hơn NLLB PyTorch, hợp CPU.",
                "Cần model CT2 đã chuẩn bị.",
                "Khuyến nghị cho tốc độ offline.",
            ),
            (
                "Local NLLB",
                "Chất lượng tốt hơn cho nhiều đoạn khó.",
                "Nặng RAM/CPU và khởi động chậm.",
                "Dùng khi ưu tiên chất lượng.",
            ),
            ("Không dịch", "Nhanh nhất.", "Không tạo bản dịch đích.", "Dùng khi văn bản nguồn đã phù hợp."),
        ],
        "model_rows": [
            (
                "nllb-200-distilled-600M",
                "Nhẹ hơn, tải nhanh hơn.",
                "Kém hơn ở câu dài hoặc thuật ngữ khó.",
                "Cần phản hồi nhanh.",
            ),
            ("nllb-200-1.3B", "Giữ nghĩa tốt hơn.", "Nặng hơn và chậm hơn.", "Xuất bản hoặc tài liệu quan trọng."),
            (
                "nllb-200-distilled-600M-ct2-int8",
                "Tối ưu tốc độ và bộ nhớ.",
                "Chất lượng đổi lấy tốc độ.",
                "Thiết lập offline khuyến nghị.",
            ),
        ],
        "advanced_items": [
            "<b>Whisper device/compute</b>: CPU + int8 an toàn, CUDA + float16 nhanh nếu GPU ổn.",
            "<b>Độ dài đoạn</b>: đoạn ngắn phản hồi nhanh hơn, đoạn dài tự nhiên hơn.",
            "<b>Lookahead</b>: tăng để ít khựng, giảm để nhẹ máy hơn.",
            "<b>VieNeu max chars</b>: giảm nếu tạo giọng local quá lâu.",
        ],
    },
    "en": {
        "title": "User guide",
        "heading": "AI Player user guide",
        "intro": "This page summarizes the main workflow and reviews the currently selected settings.",
        "tab_quick": "Workflow",
        "tab_sources": "Sources",
        "tab_evaluation": "Current setup",
        "tab_reference": "Reference",
        "quick_title": "Quick workflow",
        "quick_items": [
            "Choose a <b>Preset</b> for speed, offline use, GPU quality, or publishing.",
            "Choose a <b>Source</b>: original video, transcript, subtitle, meeting, or document editor.",
            "Adjust source/target language, translator, and TTS only when needed.",
            "Press <b>Dub / Read aloud</b>. Play may stay disabled until enough audio is buffered.",
            "If processing stalls, press <b>Reset</b> to stop the session and open a new source.",
        ],
        "slow_title": "When the app feels slow",
        "slow_items": [
            "Avoid opening multiple AI Player windows because each window may load its own models.",
            "VieNeu local TTS on CPU can take time on the first segment; use Edge TTS when speed matters.",
            "A larger buffer improves stability but increases the initial wait.",
        ],
        "supported_title": "Supported sources and formats",
        "supported_video_title": "Video files",
        "supported_website_title": "Video websites",
        "supported_document_title": "Document files",
        "supported_video_items": [
            "Local video files: <code>.mp4</code>, <code>.mkv</code>, <code>.avi</code>, <code>.mov</code>, <code>.webm</code>.",
            "Direct media URLs: <code>.mp4</code>, <code>.mkv</code>, <code>.mov</code>, <code>.webm</code>, <code>.avi</code>, <code>.m4v</code>, <code>.m3u8</code>, <code>.mpd</code>.",
            "Valid URL protocols: <code>http</code>, <code>https</code>, <code>rtsp</code>, <code>rtmp</code>, <code>mms</code>.",
        ],
        "supported_website_items": [
            "<b>Mainstream video platforms</b>: YouTube (<code>youtube.com</code>, <code>m.youtube.com</code>, <code>music.youtube.com</code>, <code>youtu.be</code>), Vimeo (<code>vimeo.com</code>), Dailymotion (<code>dailymotion.com</code>, <code>dai.ly</code>).",
            "<b>Social and short video</b>: TikTok (<code>tiktok.com</code>, <code>vm.tiktok.com</code>, <code>vt.tiktok.com</code>), Facebook (<code>facebook.com</code>, <code>m.facebook.com</code>, <code>web.facebook.com</code>, <code>fb.watch</code>), Instagram/Threads (<code>instagram.com</code>, <code>threads.net</code>), X/Twitter (<code>x.com</code>, <code>twitter.com</code>).",
            "<b>Community and chat channels</b>: Telegram (<code>t.me</code>, <code>telegram.me</code>).",
            "<b>Adult video</b>: <code>buomtv.*</code>, <code>*.buomtv.*</code>, <code>missav.ai</code>, <code>missav.com</code>, <code>missav.ws</code>, <code>supjav.com</code>, <code>javmost.com</code>, <code>javmost.cx</code>, <code>javgg.net</code>, <code>javgg.to</code>, <code>r18.com</code>, <code>javlibrary.com</code>, <code>javhd.com</code>.",
            "<b>Live/cam</b>: <code>chaturbate.com</code>, <code>chaturbate.eu</code>, <code>chaturbate.global</code>, <code>stripchat.com</code>, <code>bongacams*.com</code>, <code>bongacams*.net</code>, <code>livejasmin.com</code>, <code>cam4.com</code>, <code>camsoda.com</code>.",
        ],
        "supported_document_items": [
            "PowerPoint: <code>.pptx</code>.",
            "Word: <code>.docx</code>.",
            "PDF: <code>.pdf</code>.",
            "Text/Markdown/RTF: <code>.txt</code>, <code>.text</code>, <code>.md</code>, <code>.rtf</code>.",
            "Text data: <code>.csv</code>, <code>.json</code>.",
            "Legacy Office <code>.doc</code> and <code>.ppt</code> should be saved as <code>.docx</code> or <code>.pptx</code> before opening.",
        ],
        "evaluation_title": "Current configuration review",
        "reference_title": "Main setting reference",
        "translator_title": "Translator review",
        "model_title": "Translation model review",
        "advanced_title": "Advanced",
        "column_setting": "Setting",
        "column_current": "Current",
        "column_note": "Review",
        "column_description": "Description",
        "column_translator": "Translator",
        "column_model": "Model",
        "column_strength": "Strength",
        "column_risk": "Risk / when to avoid",
        "column_recommendation": "Recommendation",
        "column_tradeoff": "Tradeoff",
        "column_when": "Use when",
        "column_kind": "Type",
        "column_option": "Provider / Model",
        "current_setup_intro": "The tables below list the settings currently selected in the UI and describe what each one controls.",
        "reference_intro": (
            "The tables below describe the providers, models, modes, runtimes, and backends available in the UI. "
            "Local model lists can change based on the model folders installed on this machine."
        ),
        "kind_provider": "Provider",
        "kind_model": "Model",
        "kind_mode": "Mode",
        "kind_runtime": "Runtime",
        "kind_backend": "Backend",
        "yes": "On",
        "no": "Off",
        "empty_value": "Not selected",
        "configured_secret": "Configured",
        "setting_labels": {
            "preset": "Preset",
            "source": "Source",
            "translator": "Translator",
            "translation_model": "Translation model",
            "tts": "TTS",
            "voice": "Voice",
            "buffer": "Buffer",
            "target_speed": "Target audio speed",
            "whisper": "Whisper",
            "vieneu": "VieNeu",
            "tts_chars": "Max TTS characters",
        },
        "setting_notes": {
            "language": "The display language used by the UI and this guide.",
            "transcript": "Transcript file used when the source is Transcript or when existing dialogue should be read/saved.",
            "source_language": "Language of the source content; Auto lets the app detect it when possible.",
            "target_language": "Output language for translation and target voice.",
            "auto_gender": "Automatically chooses male/female voices from source audio or transcript cues when possible.",
            "voice_gender_mode": "How the app balances stable voice assignment with quick speaker changes.",
            "male_voice": "Voice used when automatic gender selection chooses male.",
            "female_voice": "Voice used when automatic gender selection chooses female.",
            "video_delay": "Delays source video so target audio has time to prepare and stay aligned.",
            "original_audio": "Source audio volume while target audio is also playing.",
            "dub_audio": "Target/dubbed voice volume.",
            "video_aspect": "Aspect ratio used for the video display area.",
            "playback_quality": "Frame quality used when opening video URLs.",
            "source_filter": "Reduces speech in the source audio to make room for target voice.",
            "source_filter_provider": "Voice filtering method: light/fast filtering or AI separation.",
            "source_filter_model": "Model used when source voice filtering runs through AI.",
            "export_video_quality": "Quality preset for dubbed video or document video export.",
            "video_url_full_cache": "Caches URL video before playback for stability, at the cost of a longer wait.",
            "asr_provider": "Speech-recognition backend used for sources that need audio transcription.",
            "whisper_device": "Device used for Whisper, such as CPU, CUDA, or Auto.",
            "whisper_compute": "Whisper compute type; int8 is lighter, float16 is faster on suitable GPUs.",
            "whisper_beam": "Beam count for recognition; higher can be more accurate but slower.",
            "whisper_vad_filter": "Filters speech segments to reduce work on silence.",
            "whisper_offline": "Uses only local Whisper models and avoids network downloads.",
            "ocr_provider": "OCR backend used for hard subtitles or image-based text.",
            "ocr_model": "OCR model or tessdata folder currently used.",
            "transcript_cleanup": "Cleanup strength applied after ASR/OCR and before translation.",
            "cleanup_provider": "Transcript cleanup backend: local, Ollama, or OpenAI-compatible API.",
            "cleanup_model": "Model used for transcript cleanup.",
            "cleanup_api_base": "API endpoint used when cleanup provider needs a server.",
            "cleanup_api_key": "API key for transcript cleanup provider, if required.",
            "translator_device": "Device used for local translation models.",
            "translation_max_tokens": "Maximum output length per translation request.",
            "translation_beams": "Beam count for translation; higher can be steadier but slower.",
            "translator_offline": "Uses only local translation models and avoids network downloads.",
            "mode": "Selected VieNeu TTS mode.",
            "model": "Selected VieNeu TTS model.",
            "vieneu_runtime": "How VieNeu TTS runs, either in-process or through a helper process.",
            "vieneu_device": "Device used for local TTS.",
            "vieneu_backend": "Acceleration backend for local TTS when available.",
            "vieneu_temperature": "Voice variation level; higher may be more varied but less stable.",
            "vieneu_offline": "Uses only local TTS resources.",
            "keep_terms": "Preserves source-language terms from the terminology file during translation.",
            "preserved_terms_file": "File containing source-language terms to keep unchanged.",
            "segment_length": "Length of each ASR/OCR/TTS processing segment.",
            "prebuffer_segments": "Number of prepared segments required before target voice starts.",
            "lookahead_segments": "Number of future segments prepared while playback is running.",
            "auto_match": "Automatically matches target voice speed and volume to source audio.",
            "speed_min": "Slowest allowed speed when auto-matching audio.",
            "speed_max": "Fastest allowed speed when auto-matching audio.",
            "gain_min": "Maximum volume reduction during automatic volume matching.",
            "gain_max": "Maximum volume boost during automatic volume matching.",
            "overlap_policy": "How the app handles target voice that risks overlapping the next segment.",
            "start_delay": "Delay before target voice generation/playback starts.",
            "capture_backend": "Backend used to capture system audio or microphone input.",
            "system_audio": "System audio device captured for live sources.",
            "microphone": "Microphone captured for meeting or microphone sources.",
            "show_transcript": "Transcript scope shown in the Transcript tab.",
            "transcript_type": "Transcript type shown: source, cleaned, or translated text.",
        },
        "translation_model_note": "The list changes with the selected translator.",
        "voice_note": "The default voice used for playback.",
        "target_speed_note": "A small increase helps timeline matching; too much can sound unnatural.",
        "whisper_note": "Only affects sources that require speech recognition.",
        "tts_chars_note": "Lower this if local voice generation takes too long.",
        "preset_unknown_note": "Custom or unknown preset.",
        "source_unknown_note": "Unknown source.",
        "translator_default_note": "Useful depending on the language pair and installed model.",
        "tts_edge_note": "Fast and light, but requires Internet.",
        "tts_vieneu_cpu_note": "Offline/local, but heavy on CPU.",
        "tts_vieneu_note": "Offline/local, best with a suitable GPU.",
        "buffer_high_note": "More stable, but starts later.",
        "buffer_low_note": "Starts faster, but may stutter.",
        "buffer_balanced_note": "Balanced for most tasks.",
        "vieneu_not_used_note": "Not used while the current TTS provider is Edge.",
        "vieneu_turbo_cpu_note": "Turbo on CPU can still be slow for long segments or busy machines.",
        "vieneu_default_note": "Useful when local/offline voice is required.",
        "label_slow": "Slow",
        "label_good": "Good",
        "label_may_slow": "May be slow",
        "label_wait": "Longer wait",
        "label_editor": "Editor",
        "label_ok": "OK",
        "finding_vieneu_cpu": "VieNeu local TTS on CPU may take a long time on the first segment, especially with Editor/Transcript.",
        "finding_edge": "Edge TTS usually responds faster and avoids loading heavy local models.",
        "finding_ct2": "NLLB CTranslate2 is a good choice for offline speed.",
        "finding_buffer": "A buffer of 20s or more improves stability but increases the initial wait.",
        "finding_editor": "Editor source is good for reading text; prefer Edge TTS when speed matters.",
        "finding_default": "The current configuration has no major risk.",
        "preset_notes": {
            "low_latency": "Quick preview with low latency, prioritizing fast response through Edge TTS.",
            "offline_lite": "No Internet required, lighter for CPU/low-end machines.",
            "balanced": "Balances speed and quality.",
            "quality": "Prioritizes GPU quality and high-quality publishing.",
        },
        "source_notes": {
            "original": "Uses the original audio from the video.",
            "system": "Captures live system audio.",
            "microphone": "Captures live microphone audio.",
            "system_microphone": "Captures system audio and microphone together.",
            "transcript": "Reads from the selected transcript file.",
            "document_editor": "Reads text typed or pasted into the editor.",
            "subtitle": "Runs OCR on burned-in video subtitles.",
        },
        "translator_notes": {
            "nllb_ct2": "Recommended for offline speed.",
            "auto": "Convenient, but may be slow because it tries multiple backends.",
            "none": "No translation; reads the source text.",
        },
        "provider_model_notes": {
            "fallback": {
                "default": {
                    "description": "Option detected from configuration or a local model folder.",
                    "when": "Use when it is installed and fits the current hardware.",
                },
                "asr_model": {
                    "description": "Whisper/Faster-Whisper model used to transcribe speech to text.",
                    "when": "Use for sources that require listening to audio, such as original video, live, or meeting.",
                },
                "ocr_model": {
                    "description": "Model or tessdata folder used to recognize text from images or burned-in subtitles.",
                    "when": "Use when the source is hard subtitles or image/document text.",
                },
                "cleanup_model": {
                    "description": "Model used to repair ASR/OCR errors, remove repetitions, and tidy dialogue.",
                    "when": "Use when raw transcript is noisy, poorly punctuated, or repetitive.",
                },
                "translation_model": {
                    "description": "Model used to translate source text to the target language.",
                    "when": "Choose based on language pair, speed needs, and installed models.",
                },
                "vieneu_model": {
                    "description": "VieNeu-TTS model for local Vietnamese voice generation.",
                    "when": "Use when local/offline voice generation or runtime control is needed.",
                },
                "source_filter_model": {
                    "description": "Model used to separate/filter source voice.",
                    "when": "Use when you want to keep background music/ambience while reducing source speech.",
                },
            },
            "asr_provider": {
                "faster_whisper": {
                    "description": (
                        "Faster-Whisper backend using CTranslate2 for faster, lighter speech recognition."
                    ),
                    "when": "Recommended default for video, live, meeting, and audio-derived transcripts.",
                }
            },
            "asr_model": {
                "faster-whisper-base": {
                    "description": (
                        "Local Whisper base model, balanced for speed, size, and basic recognition accuracy."
                    ),
                    "when": "Use on common CPU/GPU machines when fast recognition matters.",
                },
                "base": {
                    "description": "Base Whisper/Faster-Whisper variant, lightweight and quick to start.",
                    "when": "Use when speed or low-resource hardware is the priority.",
                },
            },
            "ocr_provider": {
                "tesseract": {
                    "description": "Traditional local OCR backend driven by language-specific tessdata.",
                    "when": "Use for clear burned-in subtitles or relatively clean document text.",
                }
            },
            "ocr_model": {
                "tessdata": {
                    "description": "Language data folder used by Tesseract OCR.",
                    "when": "Requires the language file matching the subtitles or document text to read.",
                }
            },
            "cleanup_provider": {
                "local": {
                    "description": "Runs the dialogue cleanup model directly on this machine.",
                    "when": "Use when offline processing is preferred and a suitable local model is installed.",
                },
                "ollama": {
                    "description": "Calls a model through a local Ollama server.",
                    "when": "Use when Ollama is running and you want flexible model switching.",
                },
                "openai": {
                    "description": "Calls an OpenAI-compatible API for dialogue cleanup.",
                    "when": "Use when an external API is acceptable and better sentence repair is desired.",
                },
            },
            "cleanup_model": {
                "Qwen2.5": {
                    "description": "Local chat model suitable for sentence repair, light denoising, and term preservation.",
                    "when": "Use for offline/local dialogue cleanup.",
                },
                "llama": {
                    "description": "Model served by Ollama/API; quality depends on the model exposed by the server.",
                    "when": "Use when the default local model is unavailable or you want to try another model.",
                },
            },
            "translator": {
                "nllb_ct2": {
                    "description": "NLLB running through CTranslate2, optimized for speed and memory.",
                    "when": "Recommended default for fast offline translation.",
                },
                "nllb": {
                    "description": "Local/PyTorch NLLB, usually heavier but useful with some full models.",
                    "when": "Use when quality matters and the machine has enough RAM/CPU/GPU.",
                },
                "none": {
                    "description": "Disables translation and keeps the source text for reading or display.",
                    "when": "Use when the source content is already in the desired language.",
                },
            },
            "translation_model": {
                "ct2": {
                    "description": "NLLB model converted to CTranslate2 for faster, lower-memory inference.",
                    "when": "Recommended for common CPU or GPU setups.",
                },
                "600M": {
                    "description": "Distilled NLLB 600M, lighter and faster to load.",
                    "when": "Use when quick response matters.",
                },
                "1.3B": {
                    "description": "Larger NLLB 1.3B model that may preserve meaning better on difficult sentences.",
                    "when": "Use when quality matters more than speed or memory use.",
                },
                "none": {
                    "description": "No model is needed while the provider is No translation.",
                    "when": "Use when the source is already suitable or only TTS is needed.",
                },
            },
            "tts": {
                "vieneu": {
                    "description": "Local/offline Vietnamese TTS, running on CPU or GPU depending on configuration.",
                    "when": "Use when offline voice generation or stable local voices are required.",
                },
                "edge": {
                    "description": "Microsoft Edge online TTS, lightweight and fast to respond.",
                    "when": "Use when Internet is available and speed is the priority.",
                },
                "none": {
                    "description": "Turns TTS off and does not create new audio.",
                    "when": "Use when only transcript/translation output or pipeline testing is needed.",
                },
            },
            "vieneu_mode": {
                "turbo": {
                    "description": "Faster VieNeu mode optimized for low response latency.",
                    "when": "Use for quick preview or when a suitable GPU is available.",
                },
                "standard": {
                    "description": "Standard VieNeu mode, potentially heavier but stable with standard models.",
                    "when": "Use when local voice quality matters and slower generation is acceptable.",
                },
            },
            "vieneu_model": {
                "Turbo": {
                    "description": "VieNeu-TTS Turbo model, prioritizing generation speed.",
                    "when": "Recommended for near real-time playback.",
                },
                "Standard": {
                    "description": "VieNeu-TTS Standard model, leaning toward quality and stability.",
                    "when": "Use for document reading or exports that are not time-sensitive.",
                },
            },
            "vieneu_runtime": {
                "subprocess": {
                    "description": "Runs TTS in a helper process to isolate native/GPU failures.",
                    "when": "Recommended default for keeping the main app more stable.",
                },
                "inprocess": {
                    "description": "Runs TTS inside the main app process, with less overhead but higher crash risk.",
                    "when": "Use only when the TTS environment is known to be stable.",
                },
                "auto": {
                    "description": "Lets the app choose the suitable runtime.",
                    "when": "Use when you are unsure which environment is best.",
                },
            },
            "vieneu_backend": {
                "auto": {
                    "description": "Automatically chooses the acceleration backend that fits the machine.",
                    "when": "Recommended for most cases.",
                },
                "native": {
                    "description": "Basic native/local backend with fewer moving parts.",
                    "when": "Use when an acceleration backend fails.",
                },
                "lmdeploy": {
                    "description": "LMDeploy acceleration backend for compatible environments.",
                    "when": "Use when the GPU/runtime supports it well and speed is needed.",
                },
            },
            "source_filter_provider": {
                "fast": {
                    "description": "Fast signal/channel-based filter with very low overhead.",
                    "when": "Use when quick voice reduction is needed and moderate separation quality is acceptable.",
                },
                "ai": {
                    "description": "Demucs/AI-based source separation, heavier but cleaner.",
                    "when": "Use when preserving background music is important and the machine is powerful enough.",
                },
            },
            "source_filter_model": {
                "htdemucs": {
                    "description": "Balanced Demucs model, commonly used for audio source separation.",
                    "when": "Recommended default for AI source voice filtering.",
                },
                "htdemucs_ft": {
                    "description": "Fine-tuned htdemucs variant.",
                    "when": "Use to compare separation quality against the default model.",
                },
                "htdemucs_6s": {
                    "description": "Demucs variant that separates more stems.",
                    "when": "Use when more detailed source separation is needed and extra load is acceptable.",
                },
                "mdx_extra": {
                    "description": "MDX extra model that may fit some music/voice mixes better.",
                    "when": "Try it when htdemucs does not produce a good result.",
                },
            },
        },
        "translator_rows": [
            (
                "NLLB CTranslate2",
                "Faster than PyTorch NLLB and CPU-friendly.",
                "Requires a prepared CT2 model.",
                "Recommended for offline speed.",
            ),
            (
                "Local NLLB",
                "Better quality on difficult passages.",
                "Heavier RAM/CPU usage and slower startup.",
                "Use when quality matters most.",
            ),
            (
                "No translation",
                "Fastest option.",
                "Does not produce target-language text.",
                "Use when the source text is already suitable.",
            ),
        ],
        "model_rows": [
            (
                "nllb-200-distilled-600M",
                "Lighter and faster to load.",
                "Weaker on long sentences or hard terminology.",
                "You need fast response.",
            ),
            ("nllb-200-1.3B", "Preserves meaning better.", "Heavier and slower.", "Publishing or important documents."),
            (
                "nllb-200-distilled-600M-ct2-int8",
                "Optimized for speed and memory.",
                "Trades some quality for speed.",
                "Recommended offline setup.",
            ),
        ],
        "advanced_items": [
            "<b>Whisper device/compute</b>: CPU + int8 is safer; CUDA + float16 is faster on a stable GPU.",
            "<b>Segment length</b>: shorter segments respond faster; longer segments can sound more natural.",
            "<b>Lookahead</b>: increase to reduce stutter, decrease to reduce load.",
            "<b>VieNeu max chars</b>: lower it if local voice generation is too slow.",
        ],
    },
}
