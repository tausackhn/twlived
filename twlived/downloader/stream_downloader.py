import asyncio
import collections
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, IO, Iterator, Optional, Set, no_type_check

import aiohttp

from .common import AwaitingStream, StreamType
from .manager import TwitchDownloadManager
from ..tracker import StreamOnline
from ..twitch import TwitchAPI
from ..utils import BaseEvent, Publisher, Subscriber, methoddispatch


class TwitchStreamDownloader(Publisher, Subscriber):
    events = [AwaitingStream]
    DEFAULT_PATH = Path('.')
    WAIT_VOD_DELAY = 10

    def __init__(self, twitch_api: TwitchAPI, *,
                 video_quality: str = 'chunked',
                 stream_type: StreamType = StreamType.VOD,
                 temporary_folder: Path = DEFAULT_PATH,
                 session: Optional[aiohttp.ClientSession] = None,
                 manager: Optional['TwitchDownloadManager'] = None) -> None:
        super().__init__()
        self.twitch_api = twitch_api
        self.video_quality = video_quality
        self.session = session or aiohttp.ClientSession(raise_for_status=True)
        self.stream_type = stream_type
        self.temporary_folder = temporary_folder
        self._manager = manager or TwitchDownloadManager(twitch_api, self.session)

        # Represents channel_id: set of datetimes
        self._downloading_streams: Dict[str, Set[datetime]] = collections.defaultdict(set)

    @property
    def manager(self) -> 'TwitchDownloadManager':
        return self._manager

    @no_type_check
    @methoddispatch
    async def handle(self, event: BaseEvent) -> None:
        pass

    @no_type_check
    @handle.register
    async def _(self, event: StreamOnline) -> None:
        # Skip if we are already downloading this stream
        if event.started_at in self._downloading_streams[event.channel_id]:
            return

        with self.create_new_file() as file, self.downloading_stream(event):
            await self.download(event, file)

    async def download(self, event: StreamOnline, file: IO[bytes]) -> None:
        if self.stream_type == StreamType.LIVE:
            await self.manager.download_live(event.channel_name, self.video_quality, file)
        elif self.stream_type == StreamType.VOD:
            vod_id = await self.wait_for_vod(event.channel_name, event.started_at)
            await self.manager.download_archive(vod_id, self.video_quality, file)

    @contextmanager
    def downloading_stream(self, event: StreamOnline) -> Iterator[None]:
        self._downloading_streams[event.channel_id].add(event.started_at)
        try:
            yield
        finally:
            self._downloading_streams[event.channel_id].remove(event.started_at)

    @contextmanager
    def create_new_file(self) -> Iterator[IO[bytes]]:
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=str(self.temporary_folder.resolve())) as file:
            logging.info('Create temporary file %s', file.name)
            yield file
            logging.info('Closing temporary file %s', file.name)

    async def wait_for_vod(self, channel: str, started_at: datetime) -> str:
        while True:
            videos = await self.twitch_api.get_videos(channel=channel, video_type='archive', limit=5)
            for video in videos:
                if abs(video.created_at - started_at) < timedelta(minutes=1):
                    return video.video_id

            await self.publish(AwaitingStream(sleep_time=self.WAIT_VOD_DELAY, channel_name=channel))
            await asyncio.sleep(TwitchStreamDownloader.WAIT_VOD_DELAY)
