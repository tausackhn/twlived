import asyncio
from itertools import chain, repeat
from typing import Dict, Iterator, List, Tuple

from .base import StreamOffline, StreamOnline, StreamTrackerBase
from ..twitch import TwitchAPI


class RegularTracker(StreamTrackerBase):
    def __init__(self, channels: List[str], twitch_api: TwitchAPI, *, poll_period: int = 60) -> None:
        super().__init__(channels)
        self.api = twitch_api
        self.poll_period = poll_period
        self._is_channel_online: Dict[str, bool] = {channel: False for channel in self.channels}

    async def run(self) -> None:
        def same_status(channel_statuses: Tuple[str, bool, bool]) -> bool:
            _, prev_status, new_status = channel_statuses
            return prev_status != new_status

        self._is_running = True
        while self.is_running:
            streams_data = await self.api.get_streams(self.channels)
            online_channels = {stream_info.channel_name: stream_info for stream_info in streams_data}

            channels_for_event = filter(same_status, ((channel, prev_status, channel in online_channels.keys())
                                                      for channel, prev_status in self._is_channel_online.items()))

            for channel, _, is_online in channels_for_event:
                if is_online:
                    await self.publish(StreamOnline.from_stream_info(online_channels[channel]))
                else:
                    await self.publish(StreamOffline(channel_name=channel))
                self._is_channel_online[channel] = is_online

            await asyncio.sleep(self.poll_period)

    async def stop(self) -> None:
        self._is_running = False


def delay_generator(maximum: int, step: int) -> Iterator[int]:
    return chain(range(step, maximum, step), repeat(maximum))


def new_delay() -> Iterator[int]:
    return delay_generator(maximum=900, step=10)
