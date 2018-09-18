import logging
import re
from contextlib import suppress
from datetime import timedelta, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, sleep
from typing import Callable, Optional, List, cast, ClassVar, Pattern, Tuple, IO
from urllib.parse import urljoin

import requests
from iso8601 import parse_date
from m3u8 import M3U8
from pydantic import BaseModel

from .events import StartDownloading, PlaylistUpdate, StopDownloading, DownloadedChunk
from .twitch_api import TwitchAPI
from .utils import retry_on_exception, Publisher, fails_in_row, chunked

log = logging.getLogger(__name__)


@retry_on_exception(requests.exceptions.RequestException, wait=5, max_tries=30)
def get_url(url: str) -> requests.Response:
    return requests.get(url, timeout=2)


class TwitchVideo(BaseModel):  # type: ignore
    created_at: str
    description: str
    duration: str
    id: str
    language: str
    published_at: str
    thumbnail_url: str
    title: str
    type: str
    url: str
    user_id: str
    view_count: int
    viewable: str

    class Config:
        ignore_extra = False
        allow_extra = True


class TwitchPlaylist:
    def __init__(self, video_id: str, quality: str, variant_playlist_fetch: Callable[[], str]) -> None:
        self.video_id = video_id
        self.quality = quality
        self._m3u8: Optional[M3U8] = None
        self._url: Optional[str] = None
        self._variant_m3u8: Optional[M3U8] = None
        self._variant_fetch: Callable[[], str] = variant_playlist_fetch

    @property
    def m3u8(self) -> M3U8:
        if not self._m3u8:
            self.update()
        return self._m3u8

    @property
    def files(self) -> List[str]:
        return self.m3u8.files  # type: ignore

    @property
    def base_uri(self) -> str:
        return urljoin(self.url, '.')

    @property
    def url(self) -> str:
        if not self._url:
            self._url = self._get_playlist_url()
        return self._url

    @retry_on_exception(requests.exceptions.RequestException, max_tries=2)
    def update(self, use_old_url: bool = False) -> None:
        if not use_old_url:
            self._url = self._get_playlist_url()
        request = get_url(self.url)
        self._m3u8 = M3U8(request.text)

    def _get_playlist_url(self) -> str:
        log.debug(f'Retrieving playlist: {self.video_id} {self.quality}')
        self._variant_m3u8 = M3U8(self._variant_fetch())
        try:
            return cast(str,
                        next(playlist.uri for playlist in self._variant_m3u8.playlists if
                             playlist.media[0].group_id == self.quality))
        except StopIteration:
            qualities = [playlist.media[0].group_id for playlist in self._variant_m3u8.playlists]
            msg = f"Got '{self.quality}' while expected one of {qualities}"
            log.exception(msg)
            raise

    def segments_after(self, last_segment: Optional[str]) -> List[str]:
        if last_segment is None:
            return self.files
        # Suppose that all segments are named like '{number}.ts' according to HLS specification
        n = int(last_segment.rstrip('.ts'))
        if n + 1 > len(self.files):
            return []
        return self.files[n + 1:]


class TwitchDownloadManager(Publisher):
    _CHUNK_SIZE = 10
    _TIME_LIMIT = _CHUNK_SIZE * 10
    _SLEEP_TIME = 30
    _DURATION_RE: ClassVar[Pattern] = re.compile(r'(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?')

    def __init__(self, twitch_api: TwitchAPI, temporary_folder: Path) -> None:
        super().__init__()
        self._twitch_api = twitch_api
        self.temporary_folder = Path(temporary_folder)

    def download(self, video_id: str, *,
                 quality: str = 'chunked',
                 video_type: Optional[str] = None) -> Tuple[TwitchVideo, Path]:
        if video_type not in TwitchAPI.VIDEO_TYPES:
            video_type = TwitchVideo(**self._twitch_api.get_videos(id=[video_id])[0][0]).broadcast_type
        if video_type != 'archive':
            raise ValueError('Only archive twitch video allowed')
        return self._download_archive(video_id, quality=quality)

    def _download_archive(self, video_id: str, quality: str) -> Tuple[TwitchVideo, Path]:
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=str(self.temporary_folder.resolve())) as file:
            log.info(f'Create temporary file {file.name}')
            playlist = TwitchPlaylist(video_id, quality=quality,
                                      variant_playlist_fetch=lambda: self._twitch_api.get_variant_playlist(video_id))
            is_downloaded = is_recording = False
            # next(exist_new_segment) - VODs info can be glitched sometime. Duration is increasing for hours but
            # no new segments are added in playlist. VOD is considered complete if there is no new segments for
            # 10*_SLEEP_TIME seconds ~ 5 minutes by default (is_downloaded = is_recording = True)
            exist_new_segment = fails_in_row(10)
            next(exist_new_segment)
            last_segment: Optional[str] = None
            log.info(f'Start downloading {video_id} with {quality} quality')
            self.publish(StartDownloading(id=video_id))
            while not is_downloaded or (is_recording and next(exist_new_segment)):
                is_recording = self._video_is_recording(video_id)
                playlist.update(use_old_url=is_downloaded)
                segments_to_load = playlist.segments_after(last_segment)
                exist_new_segment.send(bool(segments_to_load))
                self.publish(PlaylistUpdate(total_size=len(playlist.files), to_load=len(segments_to_load)))
                is_downloaded = False
                for chunk in chunked(segments_to_load, self._CHUNK_SIZE):
                    start_time = monotonic()
                    # Last downloaded or previous last_segment if no segments downloaded
                    last_segment = self._download_chunks(playlist.base_uri, chunk, write_to=file) or last_segment
                    # Downloading time exceeded. Assuming that time exceeded if no segments downloaded.
                    if monotonic() - start_time > self._TIME_LIMIT:
                        break
                else:
                    is_downloaded = True
                if is_recording and is_downloaded:
                    sleep(self._SLEEP_TIME)
            log.info(f'Downloading {video_id} with {quality} quality successful')
            self.publish(StopDownloading())
            return TwitchVideo(**self._twitch_api.get_videos(id=[video_id])[0][0]), Path(file.name)

    def _download_chunks(self, base_uri: str, segments: List[str], write_to: IO[bytes]) -> Optional[str]:
        last_segment = None
        with suppress(requests.exceptions.RequestException):
            for chunk in segments:
                write_to.write(get_url(base_uri + chunk).content)
                self.publish(DownloadedChunk())
                last_segment = chunk
        return last_segment

    def _video_is_recording(self, video_id: str) -> bool:
        video = TwitchVideo(**self._twitch_api.get_videos(id=[video_id])[0][0])
        duration_match = self._DURATION_RE.fullmatch(video.duration)
        if not duration_match or not any(duration_match.groupdict()):
            raise ValueError(f'Duration string "{video.duration}" can not be parsed')
        duration = timedelta(**{k: int(v) for k, v in duration_match.groupdict().items() if v})
        # Suppose that VOD finalized correctly
        return bool((datetime.now(timezone.utc) - (parse_date(video.created_at) + duration)) < timedelta(minutes=5))
