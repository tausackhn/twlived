import asyncio
import collections
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Deque, List, NamedTuple, Optional, Tuple, Union, cast
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientPayloadError, ClientResponseError
from m3u8 import M3U8

from .common import DownloadingError, ProgressData
from ..twitch import TwitchAPIError


class HLSSegment(NamedTuple):
    name: str
    number: int
    duration: float


class UpdatablePlaylist(ABC):
    def __init__(self, quality: str, variant_playlist_fetch: Callable[[], Awaitable[str]]) -> None:
        self.variant_playlist = variant_playlist_fetch
        self._quality = quality

        self._variant_m3u8: Optional[M3U8] = None
        self._m3u8: Optional[M3U8] = None
        self._url: Optional[str] = None

        self._update_task: Optional[asyncio.Task] = None
        self._update_stop_event = asyncio.Event()

    @property
    def quality(self) -> str:
        return self._quality

    @property
    def m3u8(self) -> M3U8:
        if self._m3u8 is None:
            raise ValueError('Call update() before using M3U8 object')
        return self._m3u8

    @property
    def url(self) -> str:
        if self._url is None:
            raise ValueError('Call update() before to get playlist url')
        return self._url

    @abstractmethod
    async def update(self, *, use_old_url: bool = True,
                     callback: Optional[Callable[[ProgressData], None]] = None) -> None:
        if not use_old_url or self._url is None:
            self._url = await self.get_playlist_url()

        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(self._url) as response:
                self._m3u8 = M3U8(await response.text())

    async def get_playlist_url(self) -> str:
        self._variant_m3u8 = M3U8(await self.variant_playlist())
        try:
            return cast(str,
                        next(playlist.uri
                             for playlist in self._variant_m3u8.playlists
                             if playlist.media[0].group_id == self.quality))
        except StopIteration as exception:
            qualities = [playlist.media[0].group_id for playlist in self._variant_m3u8.playlists]
            raise TwitchAPIError(f'Got {self.quality} while expected one of {qualities}') from exception

    def start_periodic_update(self, period: Union[int, float], *,
                              update_callback: Optional[Callable[[ProgressData], None]] = None) -> None:
        async def periodic_update(update_url: bool = False) -> None:
            # noinspection PyUnresolvedReferences
            while not (self.m3u8.is_endlist or self._update_stop_event.is_set()):
                await asyncio.sleep(period)
                await self.update(use_old_url=not update_url, callback=update_callback)
                update_url = False

        def callback(task: asyncio.Task) -> None:
            try:
                task.result()
            except (ClientResponseError, ClientPayloadError):
                self._update_task = asyncio.create_task(periodic_update(update_url=True))
                self._update_task.add_done_callback(callback)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.warning('Got an exception in playlist periodic task:', exc_info=True)
                raise

        self._update_task = asyncio.create_task(periodic_update())
        self._update_task.add_done_callback(callback)

    @abstractmethod
    def get_segments_after(self, segment: Optional[Union[str, int]] = None) -> List[Tuple[int, str]]:
        pass


class TwitchVODPlaylist(UpdatablePlaylist):
    def __init__(self, quality: str, variant_playlist_fetch: Callable[[], Awaitable[str]]) -> None:
        super().__init__(quality, variant_playlist_fetch)
        self._segments: List[Tuple[int, str]] = []

    @property
    def base_uri(self) -> str:
        return urljoin(self.url, '.')

    def get_segments_after(self, segment: Optional[Union[str, int]] = None) -> List[Tuple[int, str]]:
        if segment is None:
            return self._segments

        if isinstance(segment, str):
            # Suppose that all segments are named like '{number}[-muted].ts' according to HLS specification
            n = self.parse_segment_name(segment)
        else:
            n = segment

        if n + 1 > self._segments[-1][0]:
            return []
        return self._segments[n + 1:]

    @property
    def is_muted(self) -> bool:
        return any('muted' in file for file in self.m3u8.files)

    def get_muted_segments(self) -> List[HLSSegment]:
        return [HLSSegment(name=segment.uri,
                           number=i,
                           duration=segment.duration)
                for i, segment in enumerate(self.m3u8.segments)
                if 'muted' in segment.uri]

    async def update(self, *, use_old_url: bool = True,
                     callback: Optional[Callable[[ProgressData], None]] = None) -> None:
        await super().update(use_old_url=use_old_url)
        self._segments = list(enumerate(self.m3u8.files))
        if callback:
            callback(ProgressData(last_segment=len(self._segments)))

    @staticmethod
    def parse_segment_name(segment_name: str) -> int:
        return int(segment_name.rstrip('.ts').rstrip('-muted'))


class TwitchLivePlaylist(UpdatablePlaylist):
    MAX_SEGMENTS = 60 // 2 * 10  # 2 second long segments in  10 minutes

    def __init__(self, quality: str, variant_playlist_fetch: Callable[[], Awaitable[str]]) -> None:
        super().__init__(quality, variant_playlist_fetch)
        self._segments: Deque[Tuple[int, str]] = collections.deque(maxlen=TwitchLivePlaylist.MAX_SEGMENTS)

    @property
    def no_skips(self) -> bool:
        return all(s[1] is not None for s in self._segments)

    @property
    def is_endlist(self) -> bool:
        # noinspection PyUnresolvedReferences
        return cast(bool, self.m3u8.is_endlist)

    async def update(self, *, use_old_url: bool = False,
                     callback: Optional[Callable[[ProgressData], None]] = None) -> None:
        await super().update(use_old_url=use_old_url)

        # noinspection PyUnresolvedReferences
        first_n = self.m3u8.media_sequence
        last_n = self._segments[-1][0] if self._segments else first_n - 1

        if first_n > last_n + 1:
            # self._segments.extend((i, None) for i in range(last_n + 1, first_n))
            raise DownloadingError('Missing segment after updating live playlist')

        self._segments.extend((n, file) for n, file in enumerate(self.m3u8.files, start=first_n) if n > last_n)

        if callback:
            callback(ProgressData(last_segment=self._segments[-1][0]))

    def get_segments_after(self, segment: Optional[Union[str, int]] = None) -> List[Tuple[int, str]]:
        if segment is None:
            return list(self._segments)

        if isinstance(segment, str):
            n = next(i for i, file in enumerate(self._segments) if file[1] == segment)
        else:
            n = segment - self._segments[0][0]
        return list(self._segments)[n + 1:]
