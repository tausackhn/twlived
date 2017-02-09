# encoding=utf-8
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Dict, List

import requests
import tenacity

from updatable_m3u8 import UpdatableM3U8


class TwitchVideo:
    def __init__(self, path: str = None, info: Dict = None):
        self.info = info
        self.path = path


@tenacity.retry(retry=tenacity.retry_if_exception_type(requests.ConnectionError), wait=tenacity.wait_fixed(2))
def download_from(stream_playlist_uri: str) -> TwitchVideo:
    stream_playlist: UpdatableM3U8 = UpdatableM3U8(playlist_uri=stream_playlist_uri)
    last_segment = None

    path = NamedTemporaryFile(suffix='.ts').name
    file = open(path, 'wb')

    while True:
        stream_playlist.update()
        segments: List = _get_elements_after(stream_playlist.segments.uri, last_segment)
        last_segment = segments[-1] if len(segments) > 0 else last_segment
        i = 0
        for segment in segments:
            r: requests.Response = requests.get(segment)
            file.write(r.content)
            file.flush()
            i += 1
            print(f'{i} of {len(segments)}.')
        sleep(60)
        if stream_playlist.data['is_endlist']:
            break
    return TwitchVideo(path=path)


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
