from __future__ import annotations

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget


class VideoPlayer(QObject):
    def __init__(self, video_widget: QVideoWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._disposed = False
        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(video_widget)

    def set_video_output(self, video_widget: QVideoWidget | None) -> None:
        if self._disposed:
            return
        self._player.setVideoOutput(video_widget)

    def load(self, path: str) -> None:
        if self._disposed:
            return
        source = QUrl(path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            self._player.setSource(source)
        else:
            self._player.setSource(QUrl.fromLocalFile(path))

    def play(self) -> None:
        if self._disposed:
            return
        self._player.play()

    def pause(self) -> None:
        if self._disposed:
            return
        self._player.pause()

    def stop(self) -> None:
        if self._disposed:
            return
        self._player.stop()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._player.stop()
        self._player.setSource(QUrl())
        self._player.setVideoOutput(None)
        self._player.setAudioOutput(None)
        self._player.deleteLater()
        self._audio.deleteLater()

    def set_volume(self, value: int) -> None:
        if self._disposed:
            return
        self._audio.setVolume(max(0, min(100, value)) / 100.0)

    def set_position(self, position: float) -> None:
        if self._disposed:
            return
        duration = self.get_length_ms()
        if duration:
            self._player.setPosition(int(max(0.0, min(1.0, position)) * duration))

    def set_time_ms(self, value: int) -> None:
        if self._disposed:
            return
        self._player.setPosition(max(0, int(value)))

    def get_position(self) -> float:
        duration = self.get_length_ms()
        if not duration:
            return 0.0
        return self.get_time_ms() / duration

    def get_time_ms(self) -> int:
        if self._disposed:
            return 0
        return max(0, int(self._player.position()))

    def get_length_ms(self) -> int:
        if self._disposed:
            return 0
        return max(0, int(self._player.duration()))

    def is_playing(self) -> bool:
        if self._disposed:
            return False
        return self._player.playbackState() == QMediaPlayer.PlayingState
