from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_player_telegram_client import adapter

from ai_player.adapters.sources.telegram_channel import TelegramLoginConfig


class _FakeTelegramClient:
    def __init__(self, tmp_path: Path, *, cancel: bool = False) -> None:
        self.tmp_path = tmp_path
        self.cancel = cancel
        self.disconnected = False

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return True

    async def get_entity(self, channel: str):
        return channel

    async def get_messages(self, _entity, *, ids: int):
        return SimpleNamespace(
            id=ids,
            video=object(),
            document=SimpleNamespace(mime_type="video/mp4", size=1024, attributes=[]),
        )

    async def download_media(self, _message, *, file: str, progress_callback):
        progress_callback(512, 1024)
        progress_callback(1024, 1024)
        Path(file).write_bytes(b"video")
        return file


def test_authenticated_download_reports_cache_path_and_progress(tmp_path, monkeypatch) -> None:
    client = _FakeTelegramClient(tmp_path)
    progress = []
    monkeypatch.setattr(adapter, "TELEGRAM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(adapter, "_telegram_client", lambda _config: client)

    result = adapter.download_telegram_channel_video(
        "https://t.me/demochannel",
        "42",
        TelegramLoginConfig(123, "hash", "+84000000000"),
        progress_callback=progress.append,
        cancel_callback=lambda: False,
    )

    assert result == str(tmp_path / "demochannel-42.mp4")
    assert Path(result).read_bytes() == b"video"
    assert [item["downloaded_bytes"] for item in progress] == [0, 512, 1024]
    assert all(item["cache_dir"] == str(tmp_path) for item in progress)
    assert all(item["quality"] == "original" for item in progress)
    assert client.disconnected is True


def test_authenticated_download_cancellation_removes_partial_file(tmp_path, monkeypatch) -> None:
    client = _FakeTelegramClient(tmp_path, cancel=True)
    monkeypatch.setattr(adapter, "TELEGRAM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(adapter, "_telegram_client", lambda _config: client)

    with pytest.raises(adapter.TelegramChannelError):
        adapter.download_telegram_channel_video(
            "https://t.me/demochannel",
            "42",
            TelegramLoginConfig(123, "hash", "+84000000000"),
            cancel_callback=lambda: True,
        )

    assert not (tmp_path / "demochannel-42.mp4.part").exists()
    assert client.disconnected is True


def test_authenticated_download_reports_existing_cache(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "demochannel-42.mp4"
    output_path.write_bytes(b"cached-video")
    client = _FakeTelegramClient(tmp_path)
    progress = []
    monkeypatch.setattr(adapter, "TELEGRAM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(adapter, "_telegram_client", lambda _config: client)

    result = adapter.download_telegram_channel_video(
        "https://t.me/demochannel",
        "42",
        TelegramLoginConfig(123, "hash", "+84000000000"),
        progress_callback=progress.append,
    )

    assert result == str(output_path)
    assert len(progress) == 1
    assert progress[0]["status"] == "cached"
    assert progress[0]["downloaded_bytes"] == len(b"cached-video")
