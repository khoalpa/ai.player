from __future__ import annotations

import html

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from ai_player.core.config import AppConfig
from ai_player.services.translation import normalize_translator_provider
from ai_player.services.tts import normalize_tts_provider


class UserGuideMixin:
    def _show_user_guide(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Hướng dẫn sử dụng")
        dialog.resize(860, 720)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._user_guide_html())
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _user_guide_html(self) -> str:
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
            <h1>Hướng dẫn sử dụng AI Player</h1>
            <p class="muted">Trang này tóm tắt cách dùng nhanh và đánh giá chi tiết các setting đang chọn.</p>
            {self._quick_start_html()}
            {self._settings_evaluation_html()}
            {self._settings_reference_html()}
        </body>
        </html>
        """

    def _quick_start_html(self) -> str:
        return """
        <h2>Quy trình nhanh</h2>
        <ol>
            <li>Chọn <b>Preset</b>. <b>Nhanh online</b> ưu tiên phản hồi nhanh, <b>Offline nhẹ</b> dành cho máy yếu/không Internet, <b>Cân bằng</b> là mặc định, <b>Chất lượng GPU</b> và <b>Xuất bản / Review</b> dành cho máy CUDA.</li>
            <li>Chọn <b>Nguồn</b>: <b>Original</b> cho video, <b>Transcript</b> cho file phụ đề, <b>Editor</b> để dán văn bản và đọc như tài liệu.</li>
            <li>Chọn ngôn ngữ gốc/đích, translator và TTS nếu cần tinh chỉnh.</li>
            <li>Bấm <b>Lồng tiếng / đọc</b>. Khi app cần chuẩn bị giọng, nút Play sẽ tạm khóa cho tới khi đủ đệm.</li>
            <li>Nếu app chờ quá lâu, bấm <b>Reset</b> để dừng phiên hiện tại mà không phải thoát app.</li>
        </ol>
        <h2>Khi app bị chậm</h2>
        <ul>
            <li>Tránh mở nhiều cửa sổ AI Player cùng lúc vì mỗi cửa sổ có thể load model riêng.</li>
            <li>Với VieNeu local trên CPU, đoạn dài đầu tiên có thể mất nhiều thời gian. Dùng Edge TTS nếu ưu tiên tốc độ.</li>
            <li>Đệm cao hơn giúp phát ổn định hơn nhưng chờ lâu hơn trước khi bắt đầu.</li>
        </ul>
        """

    def _settings_evaluation_html(self) -> str:
        rows = self._current_settings_rows()
        findings = self._settings_findings()
        table_rows = "\n".join(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(value)}</td><td>{html.escape(note)}</td></tr>"
            for name, value, note in rows
        )
        finding_items = "\n".join(
            f"<li><span class='{level}'>{label}</span>: {html.escape(message)}</li>"
            for level, label, message in findings
        )
        return f"""
        <h2>Đánh giá cấu hình hiện tại</h2>
        <ul>{finding_items}</ul>
        <table>
            <tr><th>Setting</th><th>Đang chọn</th><th>Đánh giá</th></tr>
            {table_rows}
        </table>
        """

    def _settings_reference_html(self) -> str:
        return """
        <h2>Ý nghĩa các setting chính</h2>
        <h3>Cơ bản</h3>
        <ul>
            <li><b>Preset</b>: áp dụng bộ cấu hình tối ưu cho mục tiêu tốc độ/chất lượng/offline.</li>
            <li><b>Nguồn</b>: chọn dữ liệu đầu vào để dịch và tạo giọng.</li>
            <li><b>Translator</b>: <b>NLLB CTranslate2</b> thường nhanh hơn Local NLLB PyTorch trên CPU.</li>
            <li><b>TTS</b>: <b>Edge TTS</b> nhanh và nhẹ hơn nhưng cần mạng; <b>VieNeu-TTS</b> dùng local/offline nhưng nặng hơn.</li>
            <li><b>Đệm</b>: số giây giọng cần chuẩn bị trước. Cao hơn ổn định hơn, nhưng bắt đầu chậm hơn.</li>
        </ul>
        <h3>Đánh giá từng Translator</h3>
        <table>
            <tr><th>Translator</th><th>Điểm mạnh</th><th>Rủi ro / khi nào tránh</th><th>Khuyến nghị</th></tr>
            <tr>
                <td><b>Auto offline</b></td>
                <td>Tiện lợi, tự thử các backend offline có sẵn.</td>
                <td>Có thể chậm vì thử nhiều backend; khi backend đầu lỗi sẽ mất thời gian fallback.</td>
                <td>Dùng khi chưa biết máy có model nào. Không nên dùng cho preset cần phản hồi nhanh.</td>
            </tr>
            <tr>
                <td><b>NLLB CTranslate2</b></td>
                <td>Nhanh hơn Local NLLB PyTorch, phù hợp CPU, offline tốt nếu model CT2 đã có.</td>
                <td>Cần thư mục <code>models/translation/nllb-200-distilled-600M-ct2-int8</code>. Chất lượng thường thấp hơn model 1.3B.</td>
                <td>Lựa chọn mặc định nên dùng cho <b>Tốc độ</b>, <b>Cân bằng</b>, Editor/Transcript dài.</td>
            </tr>
            <tr>
                <td><b>Local NLLB</b></td>
                <td>Chất lượng tốt, dùng trực tiếp model Transformers.</td>
                <td>Nặng RAM/CPU, khởi động và dịch chậm, dễ làm app chờ lâu trên máy không có GPU.</td>
                <td>Dùng khi ưu tiên chất lượng và chấp nhận thời gian chờ.</td>
            </tr>
            <tr>
                <td><b>MarianMT / OPUS-MT</b></td>
                <td>Nhẹ cho một số cặp ngôn ngữ, đặc biệt các pipeline qua tiếng Anh.</td>
                <td>Phụ thuộc model theo từng cặp ngôn ngữ; không phải mọi cặp đều tốt.</td>
                <td>Dùng thử khi NLLB chậm hoặc khi dịch các cặp phổ biến như Anh-Việt.</td>
            </tr>
            <tr>
                <td><b>Argos offline</b></td>
                <td>Offline, nhẹ nếu gói ngôn ngữ đã cài.</td>
                <td>Chất lượng và độ phủ ngôn ngữ không ổn định; thiếu gói sẽ fallback/chậm.</td>
                <td>Chỉ dùng khi đã chuẩn bị đúng gói Argos cần thiết.</td>
            </tr>
            <tr>
                <td><b>Không dịch</b></td>
                <td>Nhanh nhất vì bỏ qua bước dịch.</td>
                <td>Giọng đọc sẽ đọc nguyên văn nguồn, không tạo bản tiếng Việt nếu nguồn không phải tiếng Việt.</td>
                <td>Dùng khi văn bản đã là tiếng Việt hoặc chỉ cần đọc nguyên văn.</td>
            </tr>
        </table>
        <h3>Đánh giá từng Model dịch</h3>
        <table>
            <tr><th>Model</th><th>Ưu điểm</th><th>Đánh đổi</th><th>Nên dùng khi</th></tr>
            <tr>
                <td><b>nllb-200-distilled-600M</b></td>
                <td>Nhẹ hơn, tải nhanh hơn, phù hợp CPU và preset nhanh.</td>
                <td>Chất lượng có thể kém hơn với câu dài, thuật ngữ chuyên ngành, hoặc ngôn ngữ xa tiếng Anh.</td>
                <td>Editor/Transcript dài, máy RAM vừa phải, cần phản hồi nhanh.</td>
            </tr>
            <tr>
                <td><b>nllb-200-1.3B</b></td>
                <td>Chất lượng tốt hơn, giữ ngữ nghĩa tốt hơn ở đoạn khó.</td>
                <td>Nặng hơn, khởi động và dịch chậm hơn, cần nhiều RAM hơn.</td>
                <td>Xuất bản cuối, tài liệu quan trọng, máy có đủ RAM/GPU hoặc chấp nhận chờ.</td>
            </tr>
            <tr>
                <td><b>nllb-200-distilled-600M-ct2-int8</b></td>
                <td>Bản CTranslate2 int8 tối ưu tốc độ và bộ nhớ.</td>
                <td>Không phải option model trong dropdown NLLB, nhưng được dùng bởi Máy dịch <b>NLLB CTranslate2</b>.</td>
                <td>Thiết lập khuyến nghị cho tốc độ offline.</td>
            </tr>
        </table>
        <h3>Nâng cao</h3>
        <ul>
            <li><b>Whisper device/compute</b>: dùng cho nhận dạng thoại từ video/audio. CPU + int8 an toàn, CUDA + float16 nhanh nếu GPU ổn.</li>
            <li><b>Độ dài đoạn</b>: đoạn ngắn phản hồi nhanh hơn, đoạn dài tự nhiên hơn nhưng dễ chờ lâu.</li>
            <li><b>Lookahead</b>: số đoạn chuẩn bị trước. Tăng để ít khựng, giảm để nhẹ máy.</li>
            <li><b>VieNeu max chars</b>: giới hạn số ký tự mỗi chunk TTS. Giảm nếu tạo giọng lâu hoặc máy yếu.</li>
        </ul>
        """

    def _current_settings_rows(self) -> list[tuple[str, str, str]]:
        config = self._current_runtime_config()
        rows = [
            ("Preset", self._combo_text(self._performance_preset_combo), self._preset_note(config.performance_preset)),
            ("Nguồn", self._combo_text(self._audio_source_combo), self._source_note(config.audio_source)),
            ("Máy dịch", self._combo_text(self._translator_combo), self._translator_note(config.translator_provider)),
            ("Model dịch", self._combo_text(self._nllb_model_combo), "Danh sách thay đổi theo Máy dịch đang chọn."),
            ("TTS", self._combo_text(self._tts_provider_combo), self._tts_note(config)),
            ("Giọng", self._combo_text(self._tts_voice_combo), "Giọng đang dùng cho phát mặc định."),
            (
                "Đệm",
                f"{int(config.dubbing_min_ready_ahead_seconds)} s",
                self._buffer_note(config.dubbing_min_ready_ahead_seconds),
            ),
            (
                "Tốc độ âm đích",
                f"{config.dubbing_speed_percent:+d} %",
                "Tăng nhẹ giúp khớp timeline, tăng quá cao có thể kém tự nhiên.",
            ),
            (
                "Whisper",
                f"{config.whisper_device} / {config.whisper_compute_type}",
                "Chỉ ảnh hưởng khi nguồn cần nhận dạng âm thanh.",
            ),
            (
                "VieNeu",
                f"{config.vieneu_tts_mode} / {config.vieneu_tts_device} / {config.vieneu_tts_backend}",
                self._vieneu_note(config),
            ),
            ("Max ký tự TTS", str(config.vieneu_tts_max_chars_chunk), "Giảm giá trị này nếu tạo giọng local bị lâu."),
        ]
        return rows

    def _settings_findings(self) -> list[tuple[str, str, str]]:
        config = self._current_runtime_config()
        findings: list[tuple[str, str, str]] = []
        tts_provider = normalize_tts_provider(config.tts_provider)
        translator_provider = normalize_translator_provider(config.translator_provider)
        if tts_provider == "vieneu" and config.vieneu_tts_device == "cpu":
            findings.append(
                ("warn", "Chậm", "VieNeu local trên CPU có thể mất lâu ở đoạn đầu, đặc biệt với Editor/Transcript.")
            )
        if tts_provider == "edge":
            findings.append(("ok", "Tốt", "Edge TTS thường phản hồi nhanh hơn và không load model local nặng."))
        if translator_provider == "auto":
            findings.append(
                (
                    "warn",
                    "Có thể chậm",
                    "Auto offline có thể thử nhiều backend. NLLB CTranslate2 ổn định hơn cho tốc độ.",
                )
            )
        elif translator_provider == "nllb_ct2":
            findings.append(("ok", "Tốt", "NLLB CTranslate2 là lựa chọn hợp lý cho tốc độ offline."))
        if config.dubbing_min_ready_ahead_seconds >= 20:
            findings.append(("warn", "Chờ lâu hơn", "Đệm 20s giúp ổn định nhưng làm thời gian chờ ban đầu dài hơn."))
        if config.audio_source == "document_editor":
            findings.append(
                ("ok", "Editor", "Nguồn Editor phù hợp để đọc văn bản, nên ưu tiên Edge TTS nếu cần nhanh.")
            )
        if not findings:
            findings.append(("ok", "Ổn", "Cấu hình hiện tại không có điểm rủi ro lớn."))
        return findings

    @staticmethod
    def _combo_text(combo: QComboBox) -> str:
        return combo.currentText() or str(combo.currentData() or "")

    @staticmethod
    def _preset_note(value: str) -> str:
        notes = {
            "fast": "Ưu tiên phản hồi nhanh, dùng Edge TTS.",
            "offline_lite": "Không cần Internet, nhẹ hơn cho CPU/máy yếu.",
            "balanced": "Mặc định, cân bằng tốc độ và chất lượng.",
            "quality": "Ưu tiên chất lượng trên máy có CUDA ổn định.",
            "review_export": "Dành cho bước rà soát và xuất bản chất lượng cao.",
        }
        return notes.get(value, "Preset tùy chỉnh hoặc chưa xác định.")

    @staticmethod
    def _source_note(value: str) -> str:
        notes = {
            "original": "Lấy âm gốc từ video.",
            "system": "Capture âm hệ thống live.",
            "microphone": "Capture micro live.",
            "system_microphone": "Capture đồng thời âm hệ thống và micro live.",
            "transcript": "Đọc theo file transcript đã chọn.",
            "document_editor": "Đọc nội dung nhập/dán trong Editor.",
            "subtitle": "OCR phụ đề cứng từ video.",
        }
        return notes.get(value, "Nguồn chưa xác định.")

    @staticmethod
    def _translator_note(value: str) -> str:
        provider = normalize_translator_provider(value)
        if provider == "nllb_ct2":
            return "Khuyến nghị cho tốc độ offline."
        if provider == "auto":
            return "Tiện lợi nhưng có thể chậm do thử nhiều backend."
        if provider == "none":
            return "Không dịch, chỉ đọc văn bản nguồn."
        return "Có thể phù hợp tùy cặp ngôn ngữ và model đã cài."

    @staticmethod
    def _tts_note(config: AppConfig) -> str:
        provider = normalize_tts_provider(config.tts_provider)
        if provider == "edge":
            return "Nhanh, nhẹ, nhưng cần internet."
        if config.vieneu_tts_device == "cpu":
            return "Offline/local nhưng nặng trên CPU."
        return "Offline/local, tốt hơn nếu có GPU phù hợp."

    @staticmethod
    def _buffer_note(value: float) -> str:
        if value >= 20:
            return "Ổn định hơn nhưng bắt đầu chậm hơn."
        if value <= 5:
            return "Bắt đầu nhanh hơn nhưng dễ khựng."
        return "Mức cân bằng cho phần lớn tác vụ."

    @staticmethod
    def _vieneu_note(config: AppConfig) -> str:
        if normalize_tts_provider(config.tts_provider) != "vieneu":
            return "Không dùng khi TTS hiện tại là Edge."
        if config.vieneu_tts_mode == "turbo" and config.vieneu_tts_device == "cpu":
            return "Turbo CPU vẫn có thể chậm khi đoạn dài hoặc máy đang tải nặng."
        return "Phù hợp khi cần giọng local/offline."
