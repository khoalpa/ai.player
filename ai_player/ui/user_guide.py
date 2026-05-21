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
        table_rows = "\n".join(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(value)}</td><td>{html.escape(note)}</td></tr>"
            for name, value, note in self._current_settings_rows()
        )
        finding_items = "\n".join(
            f"<li><span class='{level}'>{html.escape(label)}</span>: {html.escape(message)}</li>"
            for level, label, message in self._settings_findings()
        )
        return f"""
        <h2>{html.escape(text["evaluation_title"])}</h2>
        <ul>{finding_items}</ul>
        <table>
            <tr>
                <th>{html.escape(text["column_setting"])}</th>
                <th>{html.escape(text["column_current"])}</th>
                <th>{html.escape(text["column_note"])}</th>
            </tr>
            {table_rows}
        </table>
        """

    def _settings_reference_html(self) -> str:
        text = _GUIDE_TEXT[self._guide_language()]
        translator_rows = "\n".join(
            "<tr>"
            f"<td><b>{html.escape(name)}</b></td>"
            f"<td>{html.escape(strong)}</td>"
            f"<td>{html.escape(risk)}</td>"
            f"<td>{html.escape(recommendation)}</td>"
            "</tr>"
            for name, strong, risk, recommendation in text["translator_rows"]
        )
        model_rows = "\n".join(
            "<tr>"
            f"<td><b>{html.escape(name)}</b></td>"
            f"<td>{html.escape(strong)}</td>"
            f"<td>{html.escape(tradeoff)}</td>"
            f"<td>{html.escape(when)}</td>"
            "</tr>"
            for name, strong, tradeoff, when in text["model_rows"]
        )
        advanced_items = "".join(f"<li>{item}</li>" for item in text["advanced_items"])
        return f"""
        <h2>{html.escape(text["reference_title"])}</h2>
        <h3>{html.escape(text["translator_title"])}</h3>
        <table>
            <tr>
                <th>{html.escape(text["column_translator"])}</th>
                <th>{html.escape(text["column_strength"])}</th>
                <th>{html.escape(text["column_risk"])}</th>
                <th>{html.escape(text["column_recommendation"])}</th>
            </tr>
            {translator_rows}
        </table>
        <h3>{html.escape(text["model_title"])}</h3>
        <table>
            <tr>
                <th>{html.escape(text["column_model"])}</th>
                <th>{html.escape(text["column_strength"])}</th>
                <th>{html.escape(text["column_tradeoff"])}</th>
                <th>{html.escape(text["column_when"])}</th>
            </tr>
            {model_rows}
        </table>
        <h3>{html.escape(text["advanced_title"])}</h3>
        <ul>{advanced_items}</ul>
        """

    def _current_settings_rows(self) -> list[tuple[str, str, str]]:
        config = self._current_runtime_config()
        labels = _GUIDE_TEXT[self._guide_language()]["setting_labels"]
        rows = [
            (
                labels["preset"],
                self._combo_text(self._performance_preset_combo),
                self._preset_note(config.performance_preset),
            ),
            (labels["source"], self._combo_text(self._audio_source_combo), self._source_note(config.audio_source)),
            (
                labels["translator"],
                self._combo_text(self._translator_combo),
                self._translator_note(config.translator_provider),
            ),
            (
                labels["translation_model"],
                self._combo_text(self._nllb_model_combo),
                self._guide_text("translation_model_note"),
            ),
            (labels["tts"], self._combo_text(self._tts_provider_combo), self._tts_note(config)),
            (labels["voice"], self._combo_text(self._tts_voice_combo), self._guide_text("voice_note")),
            (
                labels["buffer"],
                f"{int(config.dubbing_min_ready_ahead_seconds)} s",
                self._buffer_note(config.dubbing_min_ready_ahead_seconds),
            ),
            (
                labels["target_speed"],
                f"{config.dubbing_speed_percent:+d} %",
                self._guide_text("target_speed_note"),
            ),
            (
                labels["whisper"],
                f"{config.whisper_device} / {config.whisper_compute_type} / beam {config.whisper_beam_size}",
                self._guide_text("whisper_note"),
            ),
            (
                labels["vieneu"],
                f"{config.vieneu_tts_mode} / {config.vieneu_tts_device} / {config.vieneu_tts_backend}",
                self._vieneu_note(config),
            ),
            (
                labels["tts_chars"],
                str(config.vieneu_tts_max_chars_chunk),
                self._guide_text("tts_chars_note"),
            ),
        ]
        return rows

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
        "column_translator": "Máy dịch",
        "column_model": "Model",
        "column_strength": "Điểm mạnh",
        "column_risk": "Rủi ro / khi nào tránh",
        "column_recommendation": "Khuyến nghị",
        "column_tradeoff": "Đánh đổi",
        "column_when": "Nên dùng khi",
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
        "column_translator": "Translator",
        "column_model": "Model",
        "column_strength": "Strength",
        "column_risk": "Risk / when to avoid",
        "column_recommendation": "Recommendation",
        "column_tradeoff": "Tradeoff",
        "column_when": "Use when",
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
