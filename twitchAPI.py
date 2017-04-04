# encoding=utf-8
import functools
import logging

import requests
from m3u8 import M3U8
from typing import Dict, List, Union, Callable, Tuple


def method_dispatch(func: Callable) -> Callable:
    """
    Single-dispatch class method decorator
    
    Works like functools.singledispatch for none-static class methods.
    """
    dispatcher = functools.singledispatch(func)

    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)

    wrapper.register = dispatcher.register
    functools.update_wrapper(wrapper, func)
    return wrapper


class TwitchAPI:
    """Class implementing part of Twitch API v5."""

    class VideoQuality:
        SOURCE = 'Source'
        HIGH = 'High'
        MEDIUM = 'Medium'
        LOW = 'Low'
        MOBILE = 'Mobile'
        AUDIO_ONLY = 'Audio Only'

        @staticmethod
        def get(quality: str):
            d = {'source': TwitchAPI.VideoQuality.SOURCE,
                 'high': TwitchAPI.VideoQuality.HIGH,
                 'medium': TwitchAPI.VideoQuality.MEDIUM,
                 'low': TwitchAPI.VideoQuality.LOW,
                 'mobile': TwitchAPI.VideoQuality.MOBILE,
                 'audio only': TwitchAPI.VideoQuality.AUDIO_ONLY}
            return d[quality]

    API_DOMAIN: str = 'https://api.twitch.tv'
    KRAKEN: str = '/kraken'
    API: str = '/api'
    USHER_DOMAIN: str = 'https://usher.ttvnw.net'
    _MAX_LIMIT: int = 100
    _DEFAULT_LIMIT: int = 10
    _MAX_IDS: int = 100
    headers: Dict[str, str] = {'Accept': 'application/vnd.twitchtv.v5+json'}

    def __init__(self, client_id: str):
        self.headers.update({'Client-ID': client_id})
        # Take unbound method. Make an usual function using partial()
        self._get_user_id = self._UserIDStorage(functools.partial(TwitchAPI._get_user_id_, self))

    def update_id_storage(self, channels: List[str]) -> None:
        self._get_user_id(channels)

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
        if channel_id:
            r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/channels/{channel_id}', headers=self.headers)
            return r.json()
        else:
            raise NonexistentChannel(channel)

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

    class _UserIDStorage:
        cache = {}

        def __init__(self, get_items: Callable[[List[str]], List[Tuple[str, Union[str, None]]]]):
            self._get_items = get_items

        @method_dispatch
        def __call__(self, arg):
            raise ValueError

        @__call__.register(str)
        def _(self, username: str) -> str:
            return self([username])[0]

        @__call__.register(list)
        def _(self, usernames: List[str]) -> List[Union[str, None]]:
            logging.debug(f'Retrieving user-id from IDStorage: {len(usernames)} {usernames}')
            missing_names = [_ for _ in usernames if _ not in self.cache]
            if len(missing_names) > 0:
                self._update(missing_names)
            return [self.cache[username] for username in usernames]

        def _update(self, items: List[str]) -> None:
            logging.debug(f'Updating user-id: {len(items)} {items}')
            n = TwitchAPI._MAX_IDS
            items_chunks = [items[i:i + n] for i in range(0, len(items), n)]
            for chunk in items_chunks:
                ids = self._get_items(chunk)
                self.cache.update(ids)

    def _get_user_id_(self, usernames: List[str]) -> List[Tuple[str, Union[str, None]]]:
        logging.debug(f'Retrieving user-id: {len(usernames)} {usernames}')
        if len(usernames) > TwitchAPI._MAX_IDS:
            raise TwitchAPIError('Too much usernames. Must be <= 100')
        r = requests.get(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/users',
                         headers=self.headers,
                         params={'login': ','.join(usernames)})
        if not r.ok:
            raise TwitchAPIError(f"{r.json()['error']}. {r.json()['message']}")
        users = r.json()['users']
        existing_usernames = [user['name'] for user in users]
        # Missing usernames
        ids = [(username, None) for username in usernames if username not in existing_usernames]
        # Existing usernames
        ids.extend([(user['name'], user['_id']) for user in users])
        return ids


class TwitchAPIError(Exception):
    pass


class InvalidStreamQuality(TwitchAPIError, StopIteration):
    pass


class NonexistentChannel(TwitchAPIError):
    pass


class NoValidVideo(TwitchAPIError):
    pass
