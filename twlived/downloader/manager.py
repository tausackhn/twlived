import asyncio
from datetime import datetime, timedelta, timezone
from itertools import takewhile
from pathlib import Path
from typing import Callable, IO, List, Optional, Tuple, Union, cast
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientResponseError

from .common import (BeginDownloading, BeginDownloadingLive, EndDownloading, EndDownloadingLive, ProgressData)
from .playlist import TwitchLivePlaylist, TwitchVODPlaylist
from ..twitch import StreamInfo, TwitchAPI, TwitchVideo
from ..utils import Publisher, chunked, fails_in_row, retry_on_exception, task_group, wait_group


class TwitchDownloadManager(Publisher):
    events = [BeginDownloading, EndDownloading]
    N_CONCURRENT_DOWNLOADS = 10
    PLAYLIST_UPDATES_TO_FINISH = 10
    PLAYLIST_UPDATE_PERIOD = 60
    LIVE_PLAYLIST_UPDATE_PERIOD = 2

    def __init__(self, twitch_api: TwitchAPI, session: aiohttp.ClientSession) -> None:
        super().__init__()
        self._twitch_api = twitch_api
        self._session = session

        self._progress_callback: Callable[[ProgressData], None] = empty_callback

    async def download_archive(self, video_id: str, quality: str, file: IO[bytes], *,
                               after_segment: Optional[Union[str, int]] = None) -> Tuple[TwitchVideo, Path]:
        playlist = TwitchVODPlaylist(quality, lambda: self._twitch_api.get_variant_playlist(video_id))
        video = await self._twitch_api.get_video(video_id)
        is_video_recording = await self.is_video_recording(video_id)

        await playlist.update(callback=self._progress_callback)
        first_segment_number, _ = playlist.get_segments_after(after_segment)[0]
        self._progress_callback(ProgressData(first_segment=first_segment_number))
        if is_video_recording:
            playlist.start_periodic_update(self.PLAYLIST_UPDATE_PERIOD, update_callback=self._progress_callback)

        # VODs info can be glitched sometime. Duration is increasing for hours but no new segments are added
        # to playlist. VOD is considered complete if there is no new segments many times in a row.
        exist_new_segment_before = fails_in_row(self.PLAYLIST_UPDATES_TO_FINISH)
        next(exist_new_segment_before)

        await self.publish(BeginDownloading(video_id=video.video_id, channel_name=video.channel_name))

        last_segment = after_segment
        while True:
            segments_to_load = playlist.get_segments_after(last_segment)

            # If there is no segments_to_load many times in a row downloading is considered to be done
            new_segments_exist_before = exist_new_segment_before.send(bool(segments_to_load))
            if not (new_segments_exist_before or is_video_recording):
                break

            last_successful_n = await self.download_segments(segments_to_load,
                                                             output_file=file,
                                                             base_uri=playlist.base_uri,
                                                             progress_callback=self._progress_callback,
                                                             concurrent_downloads=self.N_CONCURRENT_DOWNLOADS)
            if last_successful_n:
                last_segment = last_successful_n

            # Nothing was downloaded successfully. So, try to get a new playlist url.
            if not last_successful_n and segments_to_load:
                await playlist.update(use_old_url=False)

            is_video_recording = await self.is_video_recording(video_id)
            # Wait until new segments will be added
            if not segments_to_load:
                await asyncio.sleep(self.PLAYLIST_UPDATE_PERIOD)

        await self.publish(EndDownloading(video_id=video.video_id, channel_name=video.channel_name))
        return await self._twitch_api.get_video(video_id), Path(file.name)

    async def download_live(self, channel_name: str, quality: str, file: IO[bytes]) -> Tuple[StreamInfo, Path]:
        playlist = TwitchLivePlaylist(quality, lambda: self._twitch_api.get_live_variant_playlist(channel_name))
        await playlist.update(callback=self._progress_callback)
        first_segment_number, _ = playlist.get_segments_after()[0]
        self._progress_callback(ProgressData(first_segment=first_segment_number))
        playlist.start_periodic_update(self.LIVE_PLAYLIST_UPDATE_PERIOD,
                                       update_callback=self._progress_callback)

        await self.publish(BeginDownloadingLive(channel_name=channel_name))

        last_segment: Optional[int] = None
        while not playlist.is_endlist:
            segments_to_load = playlist.get_segments_after(last_segment)
            last_successful_n = await self.download_segments(segments_to_load,
                                                             output_file=file,
                                                             progress_callback=self._progress_callback,
                                                             concurrent_downloads=self.N_CONCURRENT_DOWNLOADS)
            if last_successful_n:
                last_segment = last_successful_n

            if not last_successful_n and segments_to_load:
                await playlist.update(use_old_url=False)

            if not segments_to_load:
                await asyncio.sleep(self.LIVE_PLAYLIST_UPDATE_PERIOD)

        await self.publish(EndDownloadingLive(channel_name=channel_name))

        return cast(StreamInfo, await self._twitch_api.get_stream(channel_name)), Path(file.name)

    @staticmethod
    async def download_segments(segments: List[Tuple[int, str]], output_file: IO[bytes], *,
                                session: Optional[aiohttp.ClientSession] = None,
                                base_uri: Optional[str] = None,
                                progress_callback: Optional[Callable[['ProgressData'], None]] = None,
                                concurrent_downloads: int = 10) -> Optional[int]:
        is_new_session = not bool(session)
        session_ = session or aiohttp.ClientSession(raise_for_status=True)
        progress_callback_ = progress_callback if progress_callback else empty_callback

        @retry_on_exception(ClientResponseError, max_tries=2, wait=1)
        async def download_segment(url: str) -> bytes:
            async with session_.get(url) as response:
                content = b''
                async for data in response.content.iter_any():
                    content += data
                    # noinspection PyTypeChecker
                    progress_callback_(ProgressData(data_size=len(data)))
                progress_callback_(ProgressData(complete_segment=1))
                return content

        last_successful_segment = None

        for chunk in chunked(segments, concurrent_downloads):
            segment_urls = map(lambda s: (urljoin(base_uri, s[1]) if base_uri else s[1],), chunk)
            tasks = task_group(download_segment, segment_urls)
            cancelled_tasks = await wait_group(tasks)

            # Sure that all tasks was done.
            for segment, task in zip(chunk, takewhile(lambda t: not (t.cancelled() or t.exception()), tasks)):
                output_file.write(task.result())
                progress_callback_(ProgressData(write_segment=1))
                last_successful_segment = segment[0]

            if cancelled_tasks:
                break

        if is_new_session:
            await session_.close()

        return last_successful_segment

    async def is_video_recording(self, video_id: str) -> bool:
        video = await self._twitch_api.get_video(video_id)
        video_ending_time = video.created_at + timedelta(seconds=video.duration)
        # Consider that video is still recording if difference between time and video ending time less than 5 minutes
        # Does not catch Twitch bug when video duration is increasing but stream has already finished.
        return datetime.now(timezone.utc) - video_ending_time < timedelta(minutes=5)

    @property
    def progress_callback(self) -> Optional[Callable[['ProgressData'], None]]:
        return self._progress_callback

    @progress_callback.setter
    def progress_callback(self, callback: Callable[['ProgressData'], None]) -> None:
        self._progress_callback = callback


def empty_callback(_: ProgressData) -> None:
    pass
