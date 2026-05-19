from __future__ import annotations

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget


class VideoPlayer(QObject):
    def __init__(self, video_widget: QVideoWidget) -> None:
        super().__init__()
        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(video_widget)

    def load(self, path: str) -> None:
        source = QUrl(path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            self._player.setSource(source)
        else:
            self._player.setSource(QUrl.fromLocalFile(path))

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def set_volume(self, value: int) -> None:
        self._audio.setVolume(max(0, min(100, value)) / 100.0)

    def set_position(self, position: float) -> None:
        duration = self.get_length_ms()
        if duration:
            self._player.setPosition(int(max(0.0, min(1.0, position)) * duration))

    def set_time_ms(self, value: int) -> None:
        self._player.setPosition(max(0, int(value)))

    def get_position(self) -> float:
        duration = self.get_length_ms()
        if not duration:
            return 0.0
        return self.get_time_ms() / duration

    def get_time_ms(self) -> int:
        return max(0, int(self._player.position()))

    def get_length_ms(self) -> int:
        return max(0, int(self._player.duration()))

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState
