from __future__ import annotations

from ai_player.core.i18n import ui_text
from ai_player.services.youtube_channel import (
    YouTubeChannelError,
    YouTubeChannelPage,
    _channel_videos_url,
    _list_youtube_public_items,
    is_youtube_channel_url,
    is_youtube_playlist_url,
)


def list_youtube_channel_items(
    value: str,
    *,
    limit: int = 50,
    continuation: str = "",
    search: str = "",
    language_id: str | None = None,
) -> YouTubeChannelPage:
    if is_youtube_playlist_url(value):
        return list_youtube_playlist_items(
            value,
            limit=limit,
            continuation=continuation,
            search=search,
            language_id=language_id,
        )
    if not is_youtube_channel_url(value):
        raise YouTubeChannelError(ui_text("youtube_channel_bad_url", language_id))
    return _list_youtube_public_items(
        _channel_videos_url(value),
        limit=limit,
        continuation=continuation,
        search=search,
        language_id=language_id,
    )


def list_youtube_playlist_items(
    value: str,
    *,
    limit: int = 50,
    continuation: str = "",
    search: str = "",
    language_id: str | None = None,
) -> YouTubeChannelPage:
    if not is_youtube_playlist_url(value):
        raise YouTubeChannelError(ui_text("youtube_playlist_bad_url", language_id))
    return _list_youtube_public_items(
        value,
        limit=limit,
        continuation=continuation,
        search=search,
        language_id=language_id,
    )
