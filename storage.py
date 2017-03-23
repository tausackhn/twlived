# encoding=utf-8
import json
import logging
import os
import shutil
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Dict, List
from urllib.parse import urljoin

import dateutil.parser
import m3u8
import requests
from tenacity import retry, retry_if_exception_type, wait_fixed

# TODO вынести в конфиг
TEMP_DIR = os.path.abspath('D:/')


class TwitchVideo:
    _schema = None

    def __init__(self, info: Dict, playlist_uri: str, file_path: str = None, false=False):
        if not TwitchVideo._schema:
            with open('video_info.schema') as json_data:
                TwitchVideo._schema = json.load(json_data)
        self._validate_info(info)
        self.info = info
        self.file_path = file_path
        self.playlist_uri = playlist_uri
        self.download_done = false

        self.title = self.info['title']
        self.broadcast_id = self.info['broadcast_id']
        self.id = self.info['_id']
        self.created_at = self.info['created_at']
        self.game = self.info['game']
        self.broadcast_type = self.info['broadcast_type']
        self.channel = self.info['channel']['name']

    def download(self):
        def get_newest(list_: List, element=None) -> List:
            if not element:
                return list_

            for i_, _ in reversed(list(enumerate(list_))):
                if _ == element:
                    return list_[i_ + 1:]
            return []

        @retry(retry=retry_if_exception_type(requests.ConnectionError), wait=wait_fixed(2))
        def download_segment(segment_: str) -> requests.Response:
            return requests.get(segment_)

        stream_playlist: _UpdatableM3U8 = _UpdatableM3U8(playlist_uri=self.playlist_uri)
        last_segment = None
        # Disable 'requests' debug message due to many 'get' calls.
        logging.getLogger().setLevel(logging.INFO)
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=TEMP_DIR) as temp_file:
            self.file_path = temp_file.name
            logging.info(f'Create temporary file {self.file_path}')
            logging.info(f'Start downloading: {self.id}')
            while True:
                stream_playlist.update()
                segments: List = get_newest(stream_playlist.segments.uri, last_segment)
                last_segment = segments[-1] if len(segments) > 0 else last_segment
                for i, segment in enumerate(segments):
                    r: requests.Response = download_segment(segment)
                    temp_file.write(r.content)
                    # TODO вынести вывод прогресса во View
                    print(f'{i+1} of {len(segments)}.')
                sleep(60)
                if stream_playlist.data['is_endlist']:
                    self.download_done = True
                    break
        logging.getLogger().setLevel(logging.DEBUG)

    @staticmethod
    def _validate_info(info):
        from jsonschema import validate
        validate(info, TwitchVideo._schema)


class Storage:
    def __init__(self, path='.'):
        self.path = os.path.abspath(path)
        os.makedirs(path, exist_ok=True)
        # TODO вынести в конфиг
        self.broadcast_path = '{id} {date:%Y-%m-%d} {title}.ts'

    def add_broadcast(self, broadcast: TwitchVideo):
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
        broadcast_path = os.path.join(self.path, new_path)
        logging.info(f'Move file to storage: {broadcast.file_path} to {broadcast_path}')
        shutil.move(broadcast.file_path, broadcast_path)


class _UpdatableM3U8:
    def __init__(self, content=None, playlist_uri=None):
        base_path: str = urljoin(playlist_uri, '.').rstrip('/') if playlist_uri else None
        self.m3u8 = m3u8.M3U8(content, base_path=base_path) if content else None
        self.playlist_uri = playlist_uri

    def __getattr__(self, item):
        return getattr(self.m3u8, item)

    def update(self):
        r = requests.get(self.playlist_uri)
        base_path: str = urljoin(self.playlist_uri, '.').rstrip('/') if self.playlist_uri else None
        self.m3u8 = m3u8.M3U8(r.text, base_path=base_path)
