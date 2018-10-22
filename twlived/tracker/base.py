from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, Union

from aiohttp.client_exceptions import ClientConnectionError, ClientPayloadError, ClientResponseError

from ..twitch import StreamInfo
from ..utils import BaseEvent, Publisher

CONNECTION_ERRORS = ClientResponseError, ClientConnectionError, ClientPayloadError


@dataclass
class StreamChanged(BaseEvent):
    channel_name: str
    channel_id: str
    game: str
    status: str
    started_at: datetime
    data: Dict[str, Any] = field(compare=False)

    @classmethod
    def from_stream_info(cls, info: StreamInfo) -> 'StreamChanged':
        return cls(channel_name=info.channel_name,
                   channel_id=info.channel_id,
                   game=info.game,
                   status=info.status,
                   started_at=info.started_at,
                   data=info.data)


@dataclass
class StreamOnline(StreamChanged):
    @classmethod
    def from_changed_event(cls, event: StreamChanged) -> 'StreamOnline':
        return cls(channel_name=event.channel_name,
                   channel_id=event.channel_id,
                   game=event.game,
                   status=event.status,
                   started_at=event.started_at,
                   data=event.data)


@dataclass
class StreamOffline(BaseEvent):
    channel_name: str


class StreamTrackerBase(Publisher, ABC):
    events = [StreamChanged, StreamOffline, StreamOnline]

    def __init__(self, channels: List[str]) -> None:
        super().__init__()
        self.channels = [channel.lower() for channel in channels]
        self._is_running = False
        self._last_event: Dict[str, Optional[BaseEvent]] = {channel: None for channel in self.channels}

    @abstractmethod
    async def run(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @property
    def is_running(self) -> bool:
        return self._is_running

    def last_event(self, channel: str) -> Optional[BaseEvent]:
        return self._last_event[channel]

    async def stream_info_to_event(self, channel: str, stream_info: Optional[StreamInfo]) -> None:
        event: Union[StreamChanged, StreamOffline]
        if stream_info:
            event = StreamChanged.from_stream_info(stream_info)
        else:
            event = StreamOffline(channel_name=channel)

        last_event = self.last_event(channel)
        if (isinstance(last_event, StreamOffline) or not last_event) and isinstance(event, StreamChanged):
            await self.publish(StreamOnline.from_changed_event(event))

        if not event == last_event:
            self._last_event[channel] = event
            await self.publish(event)


def create_tracker(cls: Type[StreamTrackerBase], *args: Any, **kwargs: Any) -> StreamTrackerBase:
    return cls(*args, **kwargs)
