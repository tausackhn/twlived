# encoding=utf-8
from urllib.parse import urljoin

import m3u8
import requests


class UpdatableM3U8:
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
