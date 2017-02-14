# encoding=utf-8
from typing import Dict, List

import requests
from m3u8 import M3U8


class TwitchAPI:
    API_DOMAIN = 'https://api.twitch.tv'
    KRAKEN = '/kraken'
    API = '/api'
    USHER_DOMAIN = 'https://usher.ttvnw.net'
    headers: Dict[str, str] = {}

    def __init__(self, headers: Dict[str, str]):
        self.headers = headers

    def get_stream_status(self, channel: str) -> str:
        r = requests.get(f'{self.API_DOMAIN}{self.KRAKEN}/streams/{channel}', headers=self.headers)
        return 'online' if r.json()['stream'] else 'offline'

    def get_video_playlist_uri(self, _id: str, quality: str = 'Source') -> str:
        vod_id = _id.lstrip('v')
        token = self._get_token(vod_id)
        qualities_playlist: M3U8 = self._get_qualities_playlist(vod_id=vod_id, token=token)
        try:
            playlist_uri = next(quality_playlist.uri for quality_playlist in qualities_playlist.playlists if
                                quality_playlist.media[0].name == quality)
            return playlist_uri
        except StopIteration as _:
            s = f"Got '{quality}' while expected one of {[_.media[0].name for _ in qualities_playlist.playlists]}"
            raise InvalidStreamQuality(s) from _

    def get_videos(self, channel: str, broadcasts: bool = True, require_all: bool = False) -> List[Dict]:
        r = requests.get(f'{self.API_DOMAIN}{self.KRAKEN}/channels/{channel}/videos',
                         headers=self.headers,
                         params={'broadcasts': 'true' if broadcasts else 'false'})  # Parameters should be strings
        videos: List[Dict] = r.json()['videos']
        while require_all and r.json()['videos']:
            next_uri = r.json()['_links']['next']
            r = requests.get(next_uri, headers=self.headers)
            videos.extend(r.json()['videos'])
        return videos

    def get_channel_info(self, channel: str) -> Dict:
        r = requests.get(f'{self.API_DOMAIN}{self.KRAKEN}/channels/{channel}', headers=self.headers)
        if r.json()['status'] != 404:
            return r.json()
        else:
            raise NonexistentChannel(r.json()['message'])

    def get_recording_video(self, channel: str) -> Dict:
        last_broadcasts = self.get_videos(channel)
        try:
            return next(broadcast for broadcast in last_broadcasts if broadcast['status'] == 'recording')
        except StopIteration as _:
            raise NoValidVideo(msg=f'No recording video at {channel}') from _

    def _get_token(self, vod_id: str) -> Dict:
        return requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.API}/vods/{vod_id}/access_token',
                            params={'need_https': 'true'},
                            headers=self.headers).json()

    def _get_qualities_playlist(self, vod_id: str, token: Dict) -> M3U8:
        r = requests.get(f'{TwitchAPI.USHER_DOMAIN}/vod/{vod_id}',
                         headers=self.headers,
                         params={'nauthsig': token['sig'],
                                 'nauth': token['token'],
                                 'allow_source': 'true'})
        return M3U8(r.text)


class TwitchAPIError(Exception):
    pass


class InvalidStreamQuality(TwitchAPIError, StopIteration):
    pass


class NonexistentChannel(TwitchAPIError):
    pass


class NoValidVideo(TwitchAPIError):
    pass
