import json
import os
import shutil
from tempfile import NamedTemporaryFile
from time import monotonic as clock
from time import sleep
from typing import Dict, List, Any, Optional, TypeVar, Iterator, IO
from urllib.parse import urljoin

# noinspection PyPackageRequirements
import dateutil.parser
from m3u8 import M3U8  # type: ignore
from requests import HTTPError
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on

from config_logging import LOG
from network import request_get_retried
from twitch_api import TwitchAPI
from view import ViewEvent, View

logger = LOG.getChild(__name__)  # pylint: disable=invalid-name

T = TypeVar('T')


class TwitchVideo:
    _schema = None

    def __init__(self, view: View, info: Dict[str, Any], api: TwitchAPI, quality: str, temp_dir: str = '.') -> None:
        if not TwitchVideo._schema:
            with open('video_info.schema') as json_data:
                TwitchVideo._schema = json.load(json_data)
        self._validate_info(info)

        self.info = info
        self.api = api
        self.quality = quality
        self.temp_dir = temp_dir
        self.view = view

        self.download_done: bool = False
        self.file: Optional[IO[bytes]] = None

    @property
    def title(self) -> str:
        return self.info['title']

    @property
    def broadcast_id(self) -> str:
        return self.info['broadcast_id']

    @property
    def id(self) -> str:
        return self.info['_id']

    @property
    def created_at(self) -> str:
        return self.info['created_at']

    @property
    def game(self) -> str:
        return self.info['game']

    @property
    def broadcast_type(self) -> str:
        return self.info['broadcast_type']

    @property
    def channel(self) -> str:
        return self.info['channel']['name']

    @property
    def is_recording(self) -> bool:
        return self.info['status'] != 'recorded'

    def download(self) -> None:
        def get_newest(_list: List[T], element: Optional[T] = None) -> List[T]:
            if not element:
                return _list
            for i, _ in reversed(list(enumerate(_list))):
                if _ == element:
                    return _list[i + 1:]
            return []

        def download_segment(segment_: str) -> bytes:
            return request_get_retried(segment_).content

        def chunks(_list: List[T], size: int) -> Iterator[List[T]]:
            for j in range(0, len(_list), size):
                yield _list[j:j + size]

        self.file = NamedTemporaryFile(suffix='.ts', delete=False, dir=self.temp_dir)
        playlist = _m3u8_from_uri(self._get_playlist_uri())
        with self.file:
            logger.info(f'Create temporary file {self.file.name}')
            logger.info(f'Start downloading: {self.id}')
            info = type('Info', (object,), dict(id=self.id, channel=self.channel))
            self.view(ViewEvent.StartDownloading, info=info)
            last_downloaded = None
            total_completed_segments = 0
            while True:
                segments = get_newest(playlist.files, last_downloaded)
                total_segments = len(playlist.files)
                completed_segments = 0
                is_slow = False
                chunks_downloaded = False
                try:
                    for chunk in chunks(segments, 10):
                        start_time = clock()
                        for segment in chunk:
                            content = download_segment(playlist.base_uri + segment)
                            self.file.write(content)
                            last_downloaded = segment
                            completed_segments += 1
                            total_completed_segments += 1
                            info = type('Info', (object,), dict(completed_segments=completed_segments,
                                                                segments=len(segments),
                                                                total_completed_segments=total_completed_segments,
                                                                total_segments=total_segments))
                            self.view(ViewEvent.ProgressInfo, info=info)
                        if clock() - start_time > 50:
                            is_slow = True
                            break
                    else:
                        chunks_downloaded = True
                except HTTPError:
                    is_slow = True
                # TODO: write a better detecting method for finished VODs.
                # TwitchAPI bug occurs sometime. Finished VOD can have 'status' == 'recording'.
                if chunks_downloaded:
                    if self.is_recording:
                        sleep(30)
                    else:
                        self.view(ViewEvent.StopDownloading)
                        break
                self._update_info()
                playlist = _m3u8_from_uri(self._get_playlist_uri() if is_slow else playlist.base_path)

    def _get_playlist_uri(self) -> str:
        return self.api.get_video_playlist_uri(self.id, group_id=self.quality)

    @staticmethod
    def _validate_info(info: Dict) -> None:
        from jsonschema import validate  # type: ignore
        validate(info, TwitchVideo._schema)

    @retry(retry=retry_on(HTTPError), wait=wait_fixed(60), stop=stop_after_attempt(30))
    def _update_info(self) -> None:
        self.info = self.api.get_video(self.id)


class Storage:
    def __init__(self, storage_path: str = '.', vod_path_template: str = '{id} {date:%Y-%m-%d}.ts') -> None:
        self.path = os.path.abspath(storage_path)
        os.makedirs(storage_path, exist_ok=True)
        self.broadcast_path = vod_path_template
        self.last_added_id: Optional[str] = None

    def add_broadcast(self, broadcast: TwitchVideo) -> None:
        if broadcast.file:
            def _sanitize(filename: str, replace_to: str = '') -> str:
                excepted_chars = list(r':;/\?|*<>.')
                for char in excepted_chars:
                    filename = filename.replace(char, replace_to)
                return filename

            new_path = self.broadcast_path.format(title=_sanitize(broadcast.title, replace_to='_'),
                                                  id=broadcast.id,
                                                  type=broadcast.broadcast_type,
                                                  channel=broadcast.channel,
                                                  game=_sanitize(broadcast.game, replace_to='_'),
                                                  date=dateutil.parser.parse(broadcast.created_at))
            new_path = os.path.join(self.path, new_path)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            while os.path.exists(new_path):
                name, ext = os.path.splitext(new_path)
                new_path = name + '+' + ext
            logger.info(f'Moving file to storage: {broadcast.file.name} to {new_path}')
            shutil.move(broadcast.file.name, new_path)
            os.chmod(new_path, 0o755)
            self.last_added_id = broadcast.id
        else:
            raise MissingFile('Broadcast has not downloaded yet')


def _m3u8_from_uri(playlist_uri: str) -> M3U8:
    base_uri = urljoin(playlist_uri, '.')
    request = request_get_retried(playlist_uri)
    return M3U8(request.text, base_path=playlist_uri, base_uri=base_uri)


class MissingFile(IOError):
    pass
