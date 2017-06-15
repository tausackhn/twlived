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

from network import request_get_retried
from twitch_api import TwitchAPI


class TwitchVideo:
    _schema = None

    def __init__(self, info: Dict, api: TwitchAPI, quality: TwitchAPI.VideoQuality, temp_dir: str = '.'):
        if not TwitchVideo._schema:
            with open('video_info.schema') as json_data:
                TwitchVideo._schema = json.load(json_data)
        self._validate_info(info)

        self.info = info
        self.api = api
        self.quality = quality
        self.temp_dir = temp_dir

        self.download_done = False
        self.file_path = None

    @property
    def title(self):
        return self.info['title']

    @property
    def broadcast_id(self):
        return self.info['broadcast_id']

    @property
    def id(self):
        return self.info['_id']

    @property
    def created_at(self):
        return self.info['created_at']

    @property
    def game(self):
        return self.info['game']

    @property
    def broadcast_type(self):
        return self.info['broadcast_type']

    @property
    def channel(self):
        return self.info['channel']['name']

    def download(self):
        def get_newest(list_: List, element=None) -> List:
            if not element:
                return list_
            for i_, _ in reversed(list(enumerate(list_))):
                if _ == element:
                    return list_[i_ + 1:]
            return []

        def download_segment(segment_: str):
            return request_get_retried(segment_)

        stream_playlist: _UpdatableM3U8 = _UpdatableM3U8(self._get_playlist_uri())
        last_segment = None
        with NamedTemporaryFile(suffix='.ts', delete=False, dir=self.temp_dir) as temp_file:
            self.file_path = temp_file.name
            logging.info(f'Create temporary file {self.file_path}')
            logging.info(f'Start downloading: {self.id}')
            while True:
                self._update_info()
                stream_playlist.update(self._get_playlist_uri())
                segments: List = get_newest(stream_playlist.segments.uri, last_segment)
                if segments:
                    last_segment = segments[-1]
                for i, segment in enumerate(segments):
                    r = download_segment(segment)
                    temp_file.write(r.content)
                    # TODO вынести вывод прогресса
                    print(f'{i+1} of {len(segments)}.')
                if self.info['status'] == 'recorded':
                    self.download_done = True
                    break
                sleep(30)

    def _get_playlist_uri(self):
        return self.api.get_video_playlist_uri(self.id, self.quality)

    @staticmethod
    def _validate_info(info: Dict):
        from jsonschema import validate
        validate(info, TwitchVideo._schema)

    def _update_info(self):
        self.info = self.api.get_video(self.id)


class Storage:
    def __init__(self, storage_path: str = '.', vod_path_template: str = '{id} {date:%Y-%m-%d}.ts'):
        self.path = os.path.abspath(storage_path)
        os.makedirs(storage_path, exist_ok=True)
        self.broadcast_path = vod_path_template

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
        new_path = os.path.join(self.path, new_path)
        logging.info(f'Moving file to storage: {broadcast.file_path} to {new_path}')
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        while os.path.exists(new_path):
            name, ext = os.path.splitext(new_path)
            new_path = name + '*' + ext
        shutil.move(broadcast.file_path, new_path)


class _UpdatableM3U8(m3u8.M3U8):
    def __init__(self, playlist_uri: str, content: str = None):
        base_path: str = urljoin(playlist_uri, '.').rstrip('/')
        super(_UpdatableM3U8, self).__init__(content, base_path=base_path)
        self.playlist_uri = playlist_uri

    def update(self, playlist_uri: str = None):
        def get_playlist(uri):
            return request_get_retried(uri)

        r = get_playlist(playlist_uri or self.playlist_uri)
        self.__init__(self.playlist_uri, r.text)
