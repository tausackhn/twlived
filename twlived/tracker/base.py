from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Type

import aiohttp

from ..twitch import StreamInfo
from ..utils import BaseEvent, Publisher

CONNECTION_ERRORS = aiohttp.ClientResponseError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError


@dataclass
class StreamOnline(BaseEvent):
    channel_name: str
    channel_id: str
    game: str
    status: str
    data: Dict[str, Any]

    @classmethod
    def from_stream_info(cls, info: StreamInfo) -> 'StreamOnline':
        return cls(channel_name=info.channel_name,
                   channel_id=info.channel_id,
                   game=info.game,
                   status=info.status,
                   data=info.data)


@dataclass
class StreamOffline(BaseEvent):
    channel_name: str


class StreamTrackerBase(Publisher, ABC):
    events = [StreamOnline]

    def __init__(self, channels: List[str]) -> None:
        super().__init__()
        self.channels = [channel.lower() for channel in channels]
        self._is_running = False

    @abstractmethod
    async def run(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @property
    def is_running(self) -> bool:
        return self._is_running


def create_tracker(cls: Type[StreamTrackerBase], *args: Any, **kwargs: Any) -> StreamTrackerBase:
    return cls(*args, **kwargs)
