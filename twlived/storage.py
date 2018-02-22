import logging
import shelve
import shutil
from contextlib import suppress
from itertools import count
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, sleep
from typing import Dict, List, Optional, TypeVar, Tuple, Callable, ClassVar, Union, Set, IO, cast
from urllib.parse import urljoin

import requests
from iso8601 import parse_date
from m3u8 import M3U8
from pydantic import BaseModel

from .events import StartDownloading, DownloadedChunk, StopDownloading, PlaylistUpdate
from .twitch_api import TwitchAPI
from .utils import Publisher, chunked, sanitize_filename, retry_on_exception

log = logging.getLogger(__name__)

T = TypeVar('T')


@retry_on_exception(requests.exceptions.RequestException, wait=5, max_tries=30)
def get_url(url: str) -> requests.Response:
    return requests.get(url, timeout=2)


class TwitchVideo(BaseModel):  # type: ignore
    title: str
    _id: str
    broadcast_id: int
    broadcast_type: str
    channel: Dict[str, Union[bool, str, int, None]]
    created_at: str
    game: str
    status: str

    @property
    def is_recording(self) -> bool:
        return self.status != 'recorded'

    @property
    def id(self) -> str:
        return self._id

    @property
    def channel_name(self) -> str:
        return cast(str, self.channel['name'])

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
    _TIME_LIMIT = _CHUNK_SIZE * 5
    _SLEEP_TIME = 30

    def __init__(self, twitch_api: TwitchAPI, temporary_folder: Path) -> None:
        super().__init__()
        self._twitch_api = twitch_api
        self.temporary_folder = Path(temporary_folder)

    def download(self, video_id: str, *, quality: str = 'chunked') -> Tuple[TwitchVideo, Path]:
        video = TwitchVideo(**self._twitch_api.get_video(video_id))
        if not video.broadcast_type == 'archive':
            raise ValueError('Only archive twitch video allowed')
        return self._download_archive(video.id, quality=quality)

    def _download_archive(self, video_id: str, quality: str) -> Tuple[TwitchVideo, Path]:
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=self.temporary_folder.resolve()) as file:
            log.info(f'Create temporary file {file.name}')
            playlist = TwitchPlaylist(video_id, quality=quality,
                                      variant_playlist_fetch=lambda: self._twitch_api.get_variant_playlist(video_id))
            is_downloaded = is_recording = False
            last_segment: Optional[str] = None
            log.info(f'Start downloading {video_id} with {quality} quality')
            self.publish(StartDownloading(id=video_id))
            while not is_downloaded or is_recording:
                is_recording = TwitchVideo(**self._twitch_api.get_video(video_id)).is_recording
                playlist.update(use_old_url=is_downloaded)
                segments_to_load = playlist.segments_after(last_segment)
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
            return TwitchVideo(**self._twitch_api.get_video(video_id)), Path(file.name)

    def _download_chunks(self, base_uri: str, segments: List[str], write_to: IO[bytes]) -> Optional[str]:
        last_segment = None
        with suppress(requests.exceptions.RequestException):
            for chunk in segments:
                write_to.write(get_url(base_uri + chunk).content)
                self.publish(DownloadedChunk())
                last_segment = chunk
        return last_segment


class Storage:
    DB_FILENAME: ClassVar[str] = 'twlived_db'
    _ALLOWED_BROADCAST_TYPES: ClassVar[Set[str]] = {'archive'}

    def __init__(self, storage_path: Union[Path, str], vod_path_template: str = '{id} {date:%Y-%m-%d}.ts') -> None:
        self.path = Path(storage_path)
        self.broadcast_template = vod_path_template
        self._vod_ids: List[str] = []
        self._create_storage_dir()
        self._db: shelve.DbfilenameShelf = shelve.DbfilenameShelf(str(self.path.joinpath(self.DB_FILENAME).resolve()))

    def added_broadcast_ids(self, broadcast_type: str) -> Set[str]:
        if broadcast_type in self._ALLOWED_BROADCAST_TYPES:
            if broadcast_type not in self._db:
                self._db[broadcast_type] = {}
            return set(self._db[broadcast_type])
        raise DBNotAllowedBroadcastType(f'{broadcast_type} are not allowed for database file')

    def add_broadcast(self, broadcast: TwitchVideo, temp_file: Path, exist_ok: bool = False) -> None:
        log.info(f'Adding broadcast {broadcast.id} related to {temp_file.resolve()}')
        if not exist_ok and broadcast.id in self._vod_ids:
            raise BroadcastExistsError(f'{broadcast.id} already added')
        if not temp_file.exists():
            raise MissingFile(f'No such file {temp_file.resolve()} when {broadcast.id} is adding')
        params = {
            'title': sanitize_filename(broadcast.title, replace_to='_'),
            'id': broadcast.id,
            'type': broadcast.broadcast_type,
            'channel': broadcast.channel_name,
            'game': sanitize_filename(broadcast.game, replace_to='_'),
            'date': parse_date(broadcast.created_at),
        }
        new_path = self.path.joinpath(Path(self.broadcast_template.format(**params)))
        new_path.parent.mkdir(parents=True, exist_ok=True)
        for i in count():
            if new_path.exists():
                new_path = new_path.with_suffix(new_path.suffix + f'.{i:02}')
            else:
                break
        log.info(f'Moving file to storage {temp_file.resolve()} to {new_path.resolve()}')
        shutil.move(temp_file, new_path)
        new_path.chmod(0o755)
        log.info(f'File {temp_file.resolve()} moved successful')
        self.update_db(broadcast, new_path)

    def _create_storage_dir(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.path.is_dir():
            raise NotADirectoryError('Storage path is not a directory')

    def update_db(self, broadcast: TwitchVideo, file: Path) -> None:
        if broadcast.id in self._db[broadcast.broadcast_type]:
            self._db[broadcast.broadcast_type][broadcast.id]['files'].append(file.relative_to(self.path))
        else:
            self._db[broadcast.broadcast_type][broadcast.id] = {
                'info': broadcast,
                'files': [file.relative_to(self.path)],
            }


class BroadcastExistsError(FileExistsError):
    pass


class MissingFile(IOError):
    pass


class DBError(BaseException):
    pass


class DBNotAllowedBroadcastType(DBError):
    pass
