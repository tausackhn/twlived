from typing import NamedTuple

from .base import JSONT


class StreamInfo(NamedTuple):
    channel_name: str
    channel_id: str
    game: str
    status: str
    data: JSONT
