import asyncio
from itertools import chain, repeat
from typing import Iterator, List, Optional, Tuple

from .base import StreamTrackerBase
from ..twitch import StreamInfo, TwitchAPI


class RegularTracker(StreamTrackerBase):
    def __init__(self, channels: List[str], twitch_api: TwitchAPI, *, poll_period: int = 60) -> None:
        super().__init__(channels)
        self.api = twitch_api
        self.poll_period = poll_period

    async def run(self) -> None:
        self._is_running = True
        while self.is_running:
            streams_data = await self.api.get_streams(self.channels)
            online_channels = {stream_info.channel_name: stream_info for stream_info in streams_data}
            offline_channels = ((channel, None) for channel in set(self.channels) - set(online_channels.keys()))
            channels_info: Iterator[Tuple[str, Optional[StreamInfo]]] = chain(online_channels.items(), offline_channels)

            for channel, stream_info in channels_info:
                await self.stream_info_to_event(channel, stream_info)

            await asyncio.sleep(self.poll_period)

    async def stop(self) -> None:
        self._is_running = False


def delay_generator(maximum: int, step: int) -> Iterator[int]:
    return chain(range(step, maximum, step), repeat(maximum))


def new_delay() -> Iterator[int]:
    return delay_generator(maximum=900, step=10)
