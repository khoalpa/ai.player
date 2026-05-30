from __future__ import annotations

import html

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTabWidget, QTextBrowser, QVBoxLayout

from ai_player.core.config import AppConfig
from ai_player.services.translation import normalize_translator_provider
from ai_player.services.tts import normalize_tts_provider
from ai_player.ui.user_guide_render import html_items, html_list, table_rows
from ai_player.ui.user_guide_text import GUIDE_TEXT


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
        return GUIDE_TEXT[self._guide_language()].get(key, key)

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
            .decision-table td:first-child, .troubleshooting-table td:first-child {{ width: 22%; font-weight: 700; }}
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
        text = GUIDE_TEXT[self._guide_language()]
        goal_rows = table_rows(text["goal_rows"])
        troubleshooting_rows = table_rows(text["troubleshooting_rows"])
        return f"""
        <h2>{html.escape(text["goal_title"])}</h2>
        <table class="decision-table">
            <tr>
                <th>{html.escape(text["column_goal"])}</th>
                <th>{html.escape(text["column_recommended_setup"])}</th>
                <th>{html.escape(text["column_note"])}</th>
            </tr>
            {goal_rows}
        </table>
        <h2>{html.escape(text["quick_title"])}</h2>
        {html_list(text["quick_items"], ordered=True)}
        <h2>{html.escape(text["slow_title"])}</h2>
        {html_list(text["slow_items"])}
        <h2>{html.escape(text["troubleshooting_title"])}</h2>
        <table class="troubleshooting-table">
            <tr>
                <th>{html.escape(text["column_symptom"])}</th>
                <th>{html.escape(text["column_try"])}</th>
            </tr>
            {troubleshooting_rows}
        </table>
        """

    def _supported_sources_html(self) -> str:
        text = GUIDE_TEXT[self._guide_language()]
        return f"""
        <h2>{html.escape(text["supported_title"])}</h2>
        <h3>{html.escape(text["supported_video_title"])}</h3>
        {html_list(text["supported_video_items"])}
        <h3>{html.escape(text["supported_website_title"])}</h3>
        {html_list(text["supported_website_items"])}
        <h3>{html.escape(text["supported_document_title"])}</h3>
        {html_list(text["supported_document_items"])}
        """

    def _settings_evaluation_html(self) -> str:
        text = GUIDE_TEXT[self._guide_language()]
        setting_tables = "\n".join(
            self._settings_group_table(title, rows) for title, rows in self._current_settings_groups()
        )
        finding_items = html_items(
            f"<span class='{level}'>{html.escape(label)}</span>: {html.escape(message)}"
            for level, label, message in self._settings_findings()
        )
        return f"""
        <h2>{html.escape(text["evaluation_title"])}</h2>
        <p class="muted">{html.escape(text["current_setup_intro"])}</p>
        <ul>{finding_items}</ul>
        {setting_tables}
        """

    def _settings_group_table(self, title: str, rows: list[tuple[str, str, str]]) -> str:
        text = GUIDE_TEXT[self._guide_language()]
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
        text = GUIDE_TEXT[self._guide_language()]
        provider_model_tables = "\n".join(
            self._reference_option_table(title, rows) for title, rows in self._provider_model_reference_groups()
        )
        return f"""
        <h2>{html.escape(text["reference_title"])}</h2>
        <p class="muted">{html.escape(text["reference_intro"])}</p>
        {provider_model_tables}
        <h3>{html.escape(text["advanced_title"])}</h3>
        {html_list(text["advanced_items"])}
        """

    def _reference_option_table(self, title: str, rows: list[tuple[str, str, str, str]]) -> str:
        text = GUIDE_TEXT[self._guide_language()]
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
        text = GUIDE_TEXT[self._guide_language()]
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
                self._tr("voice_ai_group"),
                self._option_reference_rows(self._speaker_gender_model_combo, kind_model, "speaker_gender_model")
                + self._option_reference_rows(self._source_filter_mode_combo, kind_provider, "source_filter_provider")
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
        text = GUIDE_TEXT[self._guide_language()]
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
        notes = GUIDE_TEXT[self._guide_language()]["setting_notes"]
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
                self._tr("voice_ai_group"),
                [
                    self._setting_row("speaker_gender_model", self._combo_text(self._speaker_gender_model_combo), notes["speaker_gender_model"]),
                    self._setting_row("source_filter_model", self._combo_text(self._source_filter_model_combo), notes["source_filter_model"]),
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
        text = GUIDE_TEXT[self._guide_language()]
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
        return GUIDE_TEXT[self._guide_language()]["preset_notes"].get(value, self._guide_text("preset_unknown_note"))

    def _source_note(self, value: str) -> str:
        return GUIDE_TEXT[self._guide_language()]["source_notes"].get(value, self._guide_text("source_unknown_note"))

    def _translator_note(self, value: str) -> str:
        provider = normalize_translator_provider(value)
        return GUIDE_TEXT[self._guide_language()]["translator_notes"].get(
            provider, self._guide_text("translator_default_note")
        )

    def _tts_note(self, config: AppConfig) -> str:
        text = GUIDE_TEXT[self._guide_language()]
        provider = normalize_tts_provider(config.tts_provider)
        if provider == "edge":
            return text["tts_edge_note"]
        if config.vieneu_tts_device == "cpu":
            return text["tts_vieneu_cpu_note"]
        return text["tts_vieneu_note"]

    def _buffer_note(self, value: float) -> str:
        text = GUIDE_TEXT[self._guide_language()]
        if value >= 20:
            return text["buffer_high_note"]
        if value <= 5:
            return text["buffer_low_note"]
        return text["buffer_balanced_note"]

    def _vieneu_note(self, config: AppConfig) -> str:
        text = GUIDE_TEXT[self._guide_language()]
        if normalize_tts_provider(config.tts_provider) != "vieneu":
            return text["vieneu_not_used_note"]
        if config.vieneu_tts_mode == "turbo" and config.vieneu_tts_device == "cpu":
            return text["vieneu_turbo_cpu_note"]
        return text["vieneu_default_note"]
