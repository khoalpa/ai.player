from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPushButton

from ai_player.core.config import LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH
from ai_player.ui import player_window_offline_models
from ai_player.ui.player_window import PlayerWindow


@pytest.fixture(autouse=True)
def disable_offline_models_background_startups(monkeypatch) -> None:
    monkeypatch.setattr(PlayerWindow, "_start_runtime_warmup", lambda self: None)
    monkeypatch.setattr(PlayerWindow, "_start_telegram_worker", lambda self, *args, **kwargs: None)


def test_offline_models_manager_tab_exists(qapp) -> None:
    window = PlayerWindow()
    try:
        assert hasattr(window, "_offline_models_tab_widget")
        assert "whisper" in window._offline_model_rows
        assert "adult_extractors" in window._offline_model_rows
        assert "telegram_client" in window._offline_model_rows
        assert "youtube_client" in window._offline_model_rows
        assert "backup" in window._offline_model_rows
        assert "size" in window._offline_model_rows["whisper"]
        assert window._offline_model_target_text(window._offline_model_spec("adult_extractors")) == (
            "ai-player-adult-extractors"
        )
        assert window._offline_model_target_text(window._offline_model_spec("telegram_client")) == (
            "ai-player-telegram-client"
        )
        assert window._offline_model_target_text(window._offline_model_spec("youtube_client")) == (
            "ai-player-youtube-client"
        )
        assert window._offline_model_spec("adult_extractors")["script"] == "install_adult_extractors.ps1"
        assert window._offline_model_spec("telegram_client")["script"] == "install_telegram_client.ps1"
        assert window._offline_model_spec("youtube_client")["script"] == "install_youtube_client.ps1"
        for key in ("whisper", "translation", "vieneu", "ocr", "speaker_gender"):
            button = window._offline_model_rows[key]["button"]
            assert isinstance(button, QPushButton)
            assert button.property("i18n_key") == "offline_models_download"
        assert window._offline_model_rows["adult_extractors"]["button"].property("i18n_key") == "offline_models_install"
        assert window._offline_model_rows["telegram_client"]["button"].property("i18n_key") == "offline_models_install"
        assert window._offline_model_rows["youtube_client"]["button"].property("i18n_key") == "offline_models_install"
        assert window._offline_model_rows["portable"]["button"].property("i18n_key") == "offline_models_build"
        assert window._offline_model_rows["backup"]["button"].property("i18n_key") == "offline_models_backup_action"
        assert window._offline_models_run_missing_button.property("i18n_key") == "offline_models_run_missing"
        assert window._offline_models_preview_missing_button.property("i18n_key") == "offline_models_preview_missing"
        translation_required = tuple(Path(path) for path in window._offline_model_spec("translation")["required"])
        assert Path(LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH) / "model.bin" in translation_required
        assert window._settings_tabs.count() == 8
        window._settings_tabs.setCurrentIndex(4)
        qapp.processEvents()
        assert window._settings_tab_contains(window._settings_tabs.currentWidget(), window._offline_models_tab_widget)
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_size_helpers(qapp, tmp_path) -> None:
    model_dir = tmp_path / "model"
    nested = model_dir / "nested"
    nested.mkdir(parents=True)
    (model_dir / "a.bin").write_bytes(b"a" * 1024)
    (nested / "b.bin").write_bytes(b"b" * 512)
    window = PlayerWindow()
    try:
        assert window._offline_model_path_size(model_dir) == 1536
        assert window._format_offline_model_size(1536) == "1.5 KB"
        assert window._offline_model_size_text({"key": "demo", "target": model_dir}) == "1.5 KB"
        assert window._offline_model_size_text({"key": "demo", "target": model_dir, "estimated_size": 4096}) == (
            "1.5 KB / ~4.0 KB"
        )
        missing_spec = {"key": "demo", "target": tmp_path / "missing", "estimated_size": 4096}
        assert window._offline_model_size_text(missing_spec) == "~4.0 KB"
        assert window._offline_model_size_text({"key": "plugin", "target_text": "demo-plugin"}) == "-"
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_missing_offline_model_keys_skip_utilities(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        monkeypatch.setattr(window, "_offline_model_path_ready", lambda _path: False)
        monkeypatch.setattr(window, "_offline_model_module_ready", lambda _module: False)
        assert window._missing_offline_model_keys() == (
            "whisper",
            "translation",
            "vieneu",
            "ocr",
            "speaker_gender",
            "adult_extractors",
            "telegram_client",
            "youtube_client",
        )

        monkeypatch.setattr(window, "_offline_model_path_ready", lambda _path: True)
        monkeypatch.setattr(window, "_offline_model_module_ready", lambda _module: True)
        assert window._missing_offline_model_keys() == ()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_run_missing_offline_models_starts_first_queued_task(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    started = []
    try:
        monkeypatch.setattr(window, "_missing_offline_model_keys", lambda: ("whisper", "ocr"))
        monkeypatch.setattr(window, "_start_offline_model_script", lambda key: started.append(key) or True)

        window._run_missing_offline_model_scripts()

        assert started == ["whisper"]
        assert window._offline_model_queue == ["ocr"]
        assert window._offline_model_queue_total == 2
        assert "2" in window.statusBar().currentMessage()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_preview_missing_offline_models_lists_tasks_and_sizes(qapp, tmp_path, monkeypatch) -> None:
    model_root = tmp_path / "model-a"
    model_root.mkdir()
    (model_root / "partial.bin").write_bytes(b"x" * 1024)
    specs = {
        "a": {
            "key": "a",
            "title_key": "offline_models_whisper",
            "target": model_root,
            "estimated_size": 4096,
        },
        "b": {
            "key": "b",
            "title_key": "offline_models_telegram_client",
            "target_text": "ai-player-telegram-client",
            "required_modules": ("demo.plugin",),
        },
    }
    window = PlayerWindow()
    try:
        monkeypatch.setattr(window, "_missing_offline_model_keys", lambda: ("a", "b"))
        monkeypatch.setattr(window, "_offline_model_spec", lambda key: specs[key])
        monkeypatch.setattr(
            player_window_offline_models.shutil,
            "disk_usage",
            lambda _path: SimpleNamespace(total=8192, used=1024, free=7168),
        )

        message = window._offline_model_missing_preview_text(("a", "b"))

        assert "2" in message.splitlines()[0]
        assert "3.0 KB" in message
        assert "Whisper" in message
        assert "ai-player-telegram-client" in message
        window._preview_missing_offline_model_scripts()
        assert message in window._offline_models_log.toPlainText()
        assert window.statusBar().currentMessage() == message.splitlines()[0]
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_queue_started_message_includes_progress(qapp) -> None:
    window = PlayerWindow()
    try:
        window._offline_model_queue_active = True
        window._offline_model_queue_total = 3
        window._offline_model_queue = ["ocr", "speaker_gender"]

        message = window._offline_model_started_message("whisper", window._offline_model_spec("whisper"))

        assert "1/3" in message
        assert "Whisper" in message
        window._offline_model_queue = ["speaker_gender"]
        assert "2/3" in window._offline_model_started_message("ocr", window._offline_model_spec("ocr"))
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_start_updates_status_bar(qapp, monkeypatch) -> None:
    class FakeSignal:
        def connect(self, _callback) -> None:
            return None

    class FakeProcess:
        ProcessChannelMode = SimpleNamespace(MergedChannels=object())

        def __init__(self, _parent) -> None:
            self.readyReadStandardOutput = FakeSignal()
            self.finished = FakeSignal()

        def setWorkingDirectory(self, _path) -> None:
            return None

        def setProcessChannelMode(self, _mode) -> None:
            return None

        def start(self, _program, _args) -> None:
            return None

        def waitForStarted(self, _timeout) -> bool:
            return True

    window = PlayerWindow()
    try:
        monkeypatch.setattr(player_window_offline_models.shutil, "which", lambda _name: "powershell.exe")
        monkeypatch.setattr(player_window_offline_models, "QProcess", FakeProcess)
        monkeypatch.setattr(window, "_offline_model_disk_space_warning", lambda _spec: "")

        assert window._start_offline_model_script("whisper")

        message = window._tr("offline_models_started").format(name=window._tr("offline_models_whisper"))
        assert window.statusBar().currentMessage() == message
        assert message in window._offline_models_log.toPlainText()
        assert window._background_task_details["Offline model download"] == message
        window._offline_model_process = None
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_output_updates_background_task_detail(qapp) -> None:
    class FakeProcess:
        def readAllStandardOutput(self) -> bytes:
            return b"Downloading shard 1\nModel ready\n"

    window = PlayerWindow()
    try:
        window._offline_model_process = FakeProcess()
        window._offline_model_running_message = "Running queued task 1/2: Whisper"

        window._offline_model_process_output_ready()

        assert "Model ready" in window._offline_models_log.toPlainText()
        assert window._background_task_details["Offline model download"] == (
            "Running queued task 1/2: Whisper | Model ready"
        )
        window._offline_model_process = None
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_run_missing_offline_models_checks_total_disk_space(qapp, tmp_path, monkeypatch) -> None:
    model_a = tmp_path / "model-a"
    model_b = tmp_path / "model-b"
    model_a.mkdir()
    model_b.mkdir()
    (model_a / "partial.bin").write_bytes(b"x" * 1024)
    specs = {
        "a": {"key": "a", "title_key": "offline_models_whisper", "target": model_a, "estimated_size": 4096},
        "b": {"key": "b", "title_key": "offline_models_ocr", "target": model_b, "estimated_size": 4096},
    }
    window = PlayerWindow()
    started = []
    try:
        monkeypatch.setattr(window, "_missing_offline_model_keys", lambda: ("a", "b"))
        monkeypatch.setattr(window, "_offline_model_spec", lambda key: specs[key])
        monkeypatch.setattr(window, "_start_offline_model_script", lambda key: started.append(key) or True)
        monkeypatch.setattr(
            player_window_offline_models.shutil,
            "disk_usage",
            lambda _path: SimpleNamespace(total=8192, used=4096, free=4096),
        )

        warning = window._offline_model_queue_disk_space_warning(["a", "b"])

        assert "7.0 KB" in warning
        assert "4.0 KB" in warning
        window._run_missing_offline_model_scripts()
        assert started == []
        assert window._offline_model_queue == []
        assert warning == window.statusBar().currentMessage()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_run_missing_offline_models_button_follows_missing_state(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        monkeypatch.setattr(window, "_missing_offline_model_keys", lambda: ())
        window._offline_model_process = None
        window._sync_offline_model_buttons()
        assert not window._offline_models_run_missing_button.isEnabled()

        monkeypatch.setattr(window, "_missing_offline_model_keys", lambda: ("whisper",))
        window._sync_offline_model_buttons()
        assert window._offline_models_run_missing_button.isEnabled()

        window._offline_model_process = object()
        window._sync_offline_model_buttons()
        assert not window._offline_models_run_missing_button.isEnabled()
        window._offline_model_process = None
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_queue_finished_reports_all_done(qapp, monkeypatch) -> None:
    window = PlayerWindow()
    try:
        window._offline_model_queue_active = True
        window._offline_model_queue = []
        window._offline_model_running_key = "whisper"
        monkeypatch.setattr(window, "_refresh_runtime_plugin_caches", lambda: None)
        monkeypatch.setattr(window, "_refresh_offline_model_statuses", lambda: None)
        monkeypatch.setattr(window, "_refresh_downloaded_model_combos", lambda: None)

        window._offline_model_process_finished(0, None)

        assert window._offline_model_queue_active is False
        assert window.statusBar().currentMessage() == window._tr("offline_models_missing_queue_finished")
        assert window._tr("offline_models_missing_queue_finished") in window._offline_models_log.toPlainText()
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_models_storage_summary_uses_model_size_and_disk_usage(qapp, tmp_path, monkeypatch) -> None:
    model_root = tmp_path / "models"
    model_root.mkdir()
    (model_root / "demo.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(player_window_offline_models, "MODEL_ROOT", model_root)
    monkeypatch.setattr(
        player_window_offline_models.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=4096, used=1024, free=3072),
    )
    window = PlayerWindow()
    try:
        assert (
            window._offline_models_storage_summary_text()
            == "Dung lượng model: 2.0 KB. Ổ đĩa còn trống: 3.0 KB / 4.0 KB."
        )
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_offline_model_disk_space_warning_reports_missing_free_space(qapp, tmp_path, monkeypatch) -> None:
    model_root = tmp_path / "models"
    model_root.mkdir()
    (model_root / "partial.bin").write_bytes(b"x" * 1024)
    spec = {
        "key": "demo",
        "title_key": "offline_models_whisper",
        "target": model_root,
        "estimated_size": 4096,
    }
    monkeypatch.setattr(
        player_window_offline_models.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=8192, used=7168, free=1024),
    )
    window = PlayerWindow()
    try:
        assert window._offline_model_required_free_bytes(spec) == 3072
        assert window._offline_model_disk_space_warning(spec) == (
            "Không đủ dung lượng trống cho Whisper / Faster-Whisper: cần thêm khoảng 3.0 KB, "
            "hiện chỉ còn 1.0 KB."
        )
        monkeypatch.setattr(
            player_window_offline_models.shutil,
            "disk_usage",
            lambda _path: SimpleNamespace(total=8192, used=4096, free=4096),
        )
        assert window._offline_model_disk_space_warning(spec) == ""
        window._settings_save_timer.stop()
    finally:
        window.close()
