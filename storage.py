# encoding=utf-8
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Dict, List
from urllib.parse import urljoin

import m3u8
import requests
from tenacity import retry, retry_if_exception_type, wait_fixed


class Storage:
    def __init__(self, path='.'):
        self.path = path

    def add_broadcast(self, broadcast: TwitchVideo):
        pass


class TwitchVideo:
    def __init__(self, info: Dict, playlist_uri: str, file_path: str = None):
        self.info = info
        self.file_path = file_path
        self.playlist_uri = playlist_uri
        self.download_done = False

    def download(self):
        @retry(retry=retry_if_exception_type(requests.ConnectionError), wait=wait_fixed(2))
        def download_segment(segment_: str) -> requests.Response:
            return requests.get(segment_)

        stream_playlist: _UpdatableM3U8 = _UpdatableM3U8(playlist_uri=self.playlist_uri)
        last_segment = None

        path = NamedTemporaryFile(suffix='.ts').name
        self.file_path = path
        file = open(path, 'wb')

        while True:
            stream_playlist.update()
            segments: List = _get_elements_after(stream_playlist.segments.uri, last_segment)
            last_segment = segments[-1] if len(segments) > 0 else last_segment
            for i, segment in enumerate(segments):
                r: requests.Response = download_segment(segment)
                file.write(r.content)
                file.flush()
                # FIXME calling view hook
                print(f'{i+1} of {len(segments)}.')
            sleep(60)
            if stream_playlist.data['is_endlist']:
                self.download_done = True
                break


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


def _get_elements_after(it: List, element=None) -> List:
    if element:
        _l = []
        for element_ in reversed(it):
            if element_ != element:
                _l.append(element_)
            else:
                break
        _l.reverse()
        return _l
    else:
        return it
