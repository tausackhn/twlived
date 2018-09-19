from datetime import datetime
from typing import NamedTuple

from .base import JSONT


class StreamInfo(NamedTuple):
    channel_name: str
    channel_id: str
    game: str
    status: str
    data: JSONT


class TwitchVideo(NamedTuple):
    video_id: str
    title: str
    video_type: str
    channel_name: str
    created_at: datetime
    duration: int
    data: JSONT
