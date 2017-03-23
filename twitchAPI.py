# encoding=utf-8
import logging
from functools import wraps
from typing import Dict, List, Union

import requests
from m3u8 import M3U8


def _memoized(f):
    storage = {}

    @wraps(f)
    def wrapper(self, hash_list):
        single_argument = isinstance(hash_list, str)
        if single_argument:
            hash_list = [hash_list]
        missing_hash = [_ for _ in hash_list if _ not in storage]
        if len(missing_hash) > 0:
            storage.update(dict(zip(missing_hash, f(self, missing_hash))))
        if single_argument:
            return storage[hash_list[0]]
        return [storage[key] for key in hash_list]

    return wrapper


class TwitchAPI:
    class VideoQuality:
        SOURCE = 'Source'
        HIGH = 'High'
        MEDIUM = 'Medium'
        LOW = 'Low'
        MOBILE = 'Mobile'
        AUDIO_ONLY = 'Audio Only'

    API_DOMAIN = 'https://api.twitch.tv'
    KRAKEN = '/kraken'
    API = '/api'
    USHER_DOMAIN = 'https://usher.ttvnw.net'
    _MAX_LIMIT = 100
    _DEFAULT_LIMIT = 10
    headers = {'Accept': 'application/vnd.twitchtv.v5+json'}

    def __init__(self, client_id: str):
        self.headers.update({'Client-ID': client_id})

    def get_stream_status(self, channel: str) -> str:
        logging.debug(f'Retrieving stream status: {channel}')
        channel_id = self._get_user_id(channel)
        r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/streams/{channel_id}', headers=self.headers)
        return 'online' if r.json()['stream'] else 'offline'

    def get_video_playlist_uri(self, _id: str, quality: str = VideoQuality.SOURCE) -> str:
        logging.debug(f'Retrieving playlist: {_id} {quality}')
        vod_id = _id.lstrip('v')
        token = self._get_token(vod_id)
        variant_playlist: M3U8 = self._get_variant_playlist(vod_id=vod_id, token=token)
        try:
            return next(playlist.uri for playlist in variant_playlist.playlists if
                        playlist.media[0].name == quality)
        except StopIteration as _:
            s = f"Got '{quality}' while expected one of {[_.media[0].name for _ in variant_playlist.playlists]}"
            logging.exception(s)
            raise InvalidStreamQuality(s) from _

    def get_videos(self, channel: str, broadcast_type: str = 'archive', require_all: bool = False) -> List[Dict]:
        logging.debug(f'Retrieving videos: {channel} {broadcast_type} require_all={require_all}')
        channel_id = self._get_user_id(channel)
        offset = 0
        limit = TwitchAPI._MAX_LIMIT if require_all else TwitchAPI._DEFAULT_LIMIT
        videos: List[Dict] = []

        while True:
            r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/channels/{channel_id}/videos',
                             headers=self.headers,
                             params={'broadcast_type': broadcast_type,
                                     'offset': str(offset),
                                     'limit': str(limit)})
            videos.extend(r.json()['videos'])
            if not require_all or not r.json()['videos']:
                break
            offset += TwitchAPI._MAX_LIMIT

        return videos

    def get_channel_info(self, channel: str) -> Dict:
        logging.debug(f'Retrieving channel info: {channel}')
        channel_id = self._get_user_id(channel)
        r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/channels/{channel_id}', headers=self.headers)
        if r.json()['status'] != 404:
            return r.json()
        else:
            raise NonexistentChannel(r.json()['message'])

    def get_recording_video(self, channel: str) -> Dict:
        logging.debug(f'Retrieving recording video: {channel}')
        last_broadcasts = self.get_videos(channel)
        try:
            return next(broadcast for broadcast in last_broadcasts if broadcast['status'] == 'recording')
        except StopIteration as _:
            raise NoValidVideo(f'No recording video at {channel}') from _

    def _get_token(self, vod_id: str) -> Dict:
        logging.debug(f'Retrieving token: {vod_id}')
        return requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.API}/vods/{vod_id}/access_token',
                            params={'need_https': 'true'},
                            headers=self.headers).json()

    def _get_variant_playlist(self, vod_id: str, token: Dict) -> M3U8:
        logging.debug(f'Retrieving variant playlist: {vod_id} {token}')
        r = requests.get(f'{TwitchAPI.USHER_DOMAIN}/vod/{vod_id}',
                         headers=self.headers,
                         params={'nauthsig': token['sig'],
                                 'nauth': token['token'],
                                 'allow_source': 'true',
                                 'allow_audio_only': 'true'})
        return M3U8(r.text)

    # TODO обработка разных типов аргументов через functools.singledispatch и functools.registry
    # TODO мемоизация с помощью класса
    @_memoized
    def _get_user_id(self, username: Union[List[str], str]) -> Union[List[str], str]:
        logging.debug(f'Retrieving user-id: {len(username)} {username}')
        single_arg: bool = isinstance(username, str)
        if single_arg:
            username = [username]
        if len(username) > 100:
            raise TwitchAPIError('Too much user names. Could be <= 100')
        r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/users',
                         headers=self.headers,
                         params={'login': ','.join(username)})
        if not r.json()['_total'] == len(username):
            raise NonexistentChannel('Some users does not exist')
        id = [user['_id'] for user in r.json()['users']]
        if single_arg:
            return id[0]
        return id


class TwitchAPIError(Exception):
    pass


class InvalidStreamQuality(TwitchAPIError, StopIteration):
    pass


class NonexistentChannel(TwitchAPIError):
    pass


class NoValidVideo(TwitchAPIError):
    pass
