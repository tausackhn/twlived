import shelve
import shutil
from itertools import count
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, sleep
from typing import Dict, List, Optional, TypeVar, Tuple, Any, Callable, ClassVar, Union, Set
from urllib.parse import urljoin

import requests
from iso8601 import parse_date
from m3u8 import M3U8
from pydantic import BaseModel

from config_logging import LOG
from twitch_api import TwitchAPI
from utils import split_by, chunked, sanitize_filename
from view import View

logger = LOG.getChild(__name__)

T = TypeVar('T')


class TwitchVideo(BaseModel):
    title: str
    _id: str
    broadcast_id: int
    broadcast_type: str
    channel: Dict[str, Any]
    created_at: str
    game: str
    status: str

    @property
    def is_recording(self) -> bool:
        return self.status != 'recorded'

    @property
    def id(self) -> str:
        return self._id

    class Config:
        ignore_extra = False
        allow_extra = True


class TwitchPlaylist:
    def __init__(self, video_id: str, quality: str, variant_playlist_fetch: Callable[[], str]):
        self.video_id = video_id
        self.quality = quality
        self._m3u8: Optional[M3U8] = None
        self._url: Optional[str] = None
        self._variant_m3u8: Optional[M3U8] = None
        self._variant_fetch: Callable[[], str] = variant_playlist_fetch

    @property
    def m3u8(self):
        if not self._m3u8:
            self.update()
        return self._m3u8

    @property
    def files(self):
        return self.m3u8.files

    @property
    def base_uri(self):
        return urljoin(self._url, '.')

    @property
    def url(self):
        if not self._url:
            self._url = self._get_playlist_url()
        return self._url

    def update(self, use_old_url: bool = False):
        if not use_old_url:
            self._url = self._get_playlist_url()
        # TODO: обернуть сетевые запросы
        request = requests.get(self.url)
        self._m3u8 = M3U8(request.text)

    def _get_playlist_url(self) -> str:
        logger.debug(f'Retrieving playlist: {self.video_id} {self.quality}')
        self._variant_m3u8 = M3U8(self._variant_fetch())
        try:
            return next(playlist.uri for playlist in self._variant_m3u8.playlists if
                        playlist.media[0].group_id == self.quality)
        except StopIteration:
            qualities = [playlist.media[0].group_id for playlist in self._variant_m3u8.playlists]
            msg = f"Got '{self.quality}' while expected one of {qualities}"
            logger.exception(msg)
            raise


class TwitchDownloadManager:
    _CHUNK_SIZE = 10
    _TIME_LIMIT = _CHUNK_SIZE * 5
    _SLEEP_TIME = 30

    def __init__(self, twitch_api: TwitchAPI, temporary_folder: Path):
        self._twitch_api = twitch_api
        self.temporary_folder = temporary_folder

    def download(self, video_id: str, *,
                 quality: str = 'chunked',
                 callback: View = None) -> Tuple[TwitchVideo, Path]:
        video = TwitchVideo(**self._twitch_api.get_video(video_id))
        if video.broadcast_type == 'archive':
            return self._download_archive(video.id, quality=quality, callback=callback)

    def _download_archive(self, video_id: str, quality: str,
                          callback: View = None) -> Tuple[TwitchVideo, Path]:
        # TODO: сделать вызов callback.
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=self.temporary_folder) as file:
            logger.info(f'Create temporary file {file.name}')
            playlist = TwitchPlaylist(video_id, quality=quality,
                                      variant_playlist_fetch=lambda: self._twitch_api.get_variant_playlist(video_id))
            downloaded = is_recording = False
            last_segment: Optional[str] = None
            logger.info(f'Start downloading {video_id} with {quality} quality')
            while not downloaded or is_recording:
                # TODO: обернуть сетевые запросы
                is_recording = TwitchVideo(**self._twitch_api.get_video(video_id)).is_recording
                playlist.update(use_old_url=downloaded)
                # FIXME: возможна ситуация, когда в обновлённом плейлисте ещё нет last_segment.
                # Это приведёт к загрузке всего видео с начала
                _, segments_to_load = split_by(playlist.files, last_segment)
                downloaded = False
                for chunk in chunked(segments_to_load, self._CHUNK_SIZE):
                    start_time = monotonic()
                    content, last_segment = self._download_chunks(playlist.base_uri, chunk)
                    file.write(content)
                    if monotonic() - start_time > self._TIME_LIMIT:
                        break
                else:
                    downloaded = True
                if is_recording and downloaded:
                    sleep(self._SLEEP_TIME)
            logger.info(f'Downloading {video_id} with {quality} quality successful')
            return TwitchVideo(**self._twitch_api.get_video(video_id)), Path(file.name)

    @staticmethod
    def _download_chunks(base_uri: str, segments: List[str]) -> Tuple[bytes, Optional[str]]:
        content = b''
        last_segment = None
        for chunk in segments:
            # TODO: retry download on error or throw Exception
            content += requests.get(base_uri + chunk).content
            last_segment = chunk
        return content, last_segment


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
        logger.info(f'Adding broadcast {broadcast.id} related to {temp_file.resolve()}')
        if not exist_ok and broadcast.id in self._vod_ids:
            raise BroadcastExistsError(f'{broadcast.id} already added')
        if not temp_file.exists():
            raise MissingFile(f'No such file {temp_file.resolve()} when {broadcast.id} is adding')
        params = {
            'title': sanitize_filename(broadcast.title, replace_to='_'),
            'id': broadcast.id,
            'type': broadcast.broadcast_type,
            'channel': broadcast.channel,
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
        logger.info(f'Moving file to storage {temp_file.resolve()} to {new_path.resolve()}')
        shutil.move(temp_file, new_path)
        new_path.chmod(0o755)
        logger.info(f'File {temp_file.resolve()} moved successful')
        self.update_db(broadcast, new_path)

    def _create_storage_dir(self):
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.path.is_dir():
            raise NotADirectoryError('Storage path is not a directory')

    def update_db(self, broadcast: TwitchVideo, file: Path):
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
