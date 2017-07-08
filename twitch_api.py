# encoding=utf-8
import functools
import json
import logging
from time import time as utc
from typing import Dict, List, Callable, Tuple, Any, TypeVar, Optional
from urllib.parse import urljoin

import requests
from m3u8 import M3U8  # type: ignore

T = TypeVar('T')


def method_dispatch(func: Callable[..., T]) -> Callable[..., T]:
    """
    Single-dispatch class method decorator
    Works like functools.singledispatch for none-static class methods.
    """
    dispatcher = functools.singledispatch(func)

    @functools.wraps(func)
    def wrapper(*args: Any, **_: Any) -> T:
        return dispatcher.dispatch(args[1].__class__)(*args, **_)

    wrapper.register = dispatcher.register
    return wrapper


def token_storage(func: Callable[[Any, str], Dict]) -> Callable[[Any, str], Dict]:
    """
    Cached storage for playlist tokens.
    Token expires after ~21 hours. Saves one request, when one gets VOD playlist
    """
    # FIXME: implement deleting time expired tokens
    storage: Dict[str, Tuple[Dict, int]] = {}

    @functools.wraps(func)
    def wrapper(self: Any, vod_id: str) -> Dict:
        if vod_id not in storage or storage[vod_id][1] < utc():
            token = func(self, vod_id)
            storage[vod_id] = (token, json.loads(token['token'])['expires'])
        return storage[vod_id][0]

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
        def get(quality: str) -> str:
            qualities = {'source': TwitchAPI.VideoQuality.SOURCE,
                         'high': TwitchAPI.VideoQuality.HIGH,
                         'medium': TwitchAPI.VideoQuality.MEDIUM,
                         'low': TwitchAPI.VideoQuality.LOW,
                         'mobile': TwitchAPI.VideoQuality.MOBILE,
                         'audio only': TwitchAPI.VideoQuality.AUDIO_ONLY}
            return qualities[quality]

    API_DOMAIN: str = 'https://api.twitch.tv'
    KRAKEN: str = '/kraken'
    API: str = '/api'
    USHER_DOMAIN: str = 'https://usher.ttvnw.net'
    MAX_VIDEOS: int = 100
    DEFAULT_NUM_VIDEOS: int = 10
    MAX_IDS: int = 100
    headers: Dict[str, str] = {'Accept': 'application/vnd.twitchtv.v5+json'}

    def __init__(self, client_id: str, fetch: Callable = requests.get) -> None:
        self.headers.update({'Client-ID': client_id})
        self._fetch = fetch
        # Take unbound method. Make an usual function using partial()
        self._get_user_id = self._UserIDStorage(functools.partial(TwitchAPI._get_user_id_, self))

    def update_id_storage(self, channels: List[str]) -> None:
        self._get_user_id(channels)

    def get_stream(self, channel: str) -> Dict:
        logging.debug(f'Retrieving stream status: {channel}')
        channel_id = self._get_user_id(channel)
        r = self._request_get(f'streams/{channel_id}')
        r.raise_for_status()
        return r.json()

    def get_stream_status(self, channel: str) -> str:
        streams = self.get_streams([channel])
        return 'online' if streams['_total'] > 0 else 'offline'

    def get_streams(self,
                    channel: Optional[List[str]] = None,
                    game: Optional[str] = None,
                    language: Optional[str] = None,
                    stream_type: Optional[str] = None,
                    limit: int = 25, offset: int = 0) -> Dict:
        if isinstance(channel, list):
            logging.debug(f'Retrieving streams info: {len(channel)} {channel}')
        else:
            logging.debug(f'Retrieving streams info: {game}, {language}, {stream_type}, {limit}, {offset}')
        if limit > 100:
            raise TwitchAPIError('Too much streams requested. Must be <= 100')
        channel_ids = self._get_user_id(channel) if channel else None
        if channel_ids and None in channel_ids:
            raise NonexistentChannel(f'Some channels in {channel} are not exist')
        params = {'channel': ','.join(channel_ids) if channel_ids else None,
                  'game': game,
                  'language': language,
                  'stream_type': stream_type,
                  'limit': str(limit),
                  'offset': str(offset)}
        params = {key: value for key, value in params.items() if value}
        r = self._request_get('streams', params=params)
        return r.json()

    def get_video_playlist_uri(self, _id: str, quality: str = VideoQuality.SOURCE) -> str:
        logging.debug(f'Retrieving playlist: {_id} {quality}')
        vod_id = _id.lstrip('v')
        token = self._get_token(vod_id)
        variant_playlist: M3U8 = self._get_variant_playlist(vod_id=vod_id, token=token)
        try:
            return next(playlist.uri for playlist in variant_playlist.playlists if
                        playlist.media[0].name == quality)
        except StopIteration as _:
            msg = f"Got '{quality}' while expected one of {[_.media[0].name for _ in variant_playlist.playlists]}"
            logging.exception(msg)
            raise InvalidStreamQuality(msg) from _

    def get_videos(self, channel: str, broadcast_type: str = 'archive', require_all: bool = False) -> List[Dict]:
        logging.debug(f'Retrieving videos: {channel} {broadcast_type} require_all={require_all}')
        channel_id = self._get_user_id(channel)
        offset = 0
        limit = TwitchAPI.MAX_VIDEOS if require_all else TwitchAPI.DEFAULT_NUM_VIDEOS
        videos: List[Dict] = []

        while True:
            r = self._request_get(f'channels/{channel_id}/videos',
                                  params={'broadcast_type': broadcast_type,
                                          'offset': str(offset),
                                          'limit': str(limit)})
            videos.extend(r.json()['videos'])
            if not require_all or not r.json()['videos']:
                break
            offset += TwitchAPI.MAX_VIDEOS

        return videos

    def get_video(self, id_: str) -> Dict:
        logging.debug(f'Retrieving video: {id_}')
        r = self._request_get(f'videos/{id_}')
        return r.json()

    def get_channel_info(self, channel: str) -> Dict:
        logging.debug(f'Retrieving channel info: {channel}')
        channel_id = self._get_user_id(channel)
        if channel_id:
            r = self._request_get(f'channels/{channel_id}')
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

    @token_storage
    def _get_token(self, vod_id: str) -> Dict:
        logging.debug(f'Retrieving token: {vod_id}')
        r = self._request_get(f'vods/{vod_id}/access_token',
                              domain=f'{TwitchAPI.API_DOMAIN}{TwitchAPI.API}/',
                              params={'need_https': 'true'})
        return r.json()

    def _get_variant_playlist(self, vod_id: str, token: Dict) -> M3U8:
        logging.debug(f'Retrieving variant playlist: {vod_id} {token}')
        r = self._request_get(f'vod/{vod_id}', domain=TwitchAPI.USHER_DOMAIN,
                              params={'nauthsig': token['sig'],
                                      'nauth': token['token'],
                                      'allow_source': 'true',
                                      'allow_audio_only': 'true'})
        return M3U8(r.text)

    class _UserIDStorage:
        """
        Class, which caches {username: user ID} for API methods.
        Saves one request, when one uses method by username.
        """
        cache: Dict[str, Optional[str]] = {}

        def __init__(self, get_items: Callable[[List[str]], List[Tuple[str, Optional[str]]]]) -> None:
            self._get_items = get_items

        @method_dispatch
        def __call__(self, arg: Any) -> Any:
            raise ValueError

        @__call__.register(str)
        def _str(self, username: str) -> str:
            return self([username])[0]

        @__call__.register(list)
        def _list(self, usernames: List[str]) -> List[Optional[str]]:
            logging.debug(f'Retrieving user-id from IDStorage: {len(usernames)} {usernames}')
            missing_names = [_ for _ in usernames if _ not in self.cache]
            if missing_names:
                self._update(missing_names)
            return [self.cache[username] for username in usernames]

        def _update(self, items: List[str]) -> None:
            logging.debug(f'Updating user-id: {len(items)} {items}')
            max_id = TwitchAPI.MAX_IDS
            items_chunks = [items[i:i + max_id] for i in range(0, len(items), max_id)]
            for chunk in items_chunks:
                ids = self._get_items(chunk)
                self.cache.update(ids)

    def _get_user_id_(self, usernames: List[str]) -> List[Tuple[str, Optional[str]]]:
        logging.debug(f'Retrieving user-id: {len(usernames)} {usernames}')
        if len(usernames) > TwitchAPI.MAX_IDS:
            raise TwitchAPIError('Too much usernames. Must be <= 100')
        r = self._request_get('users', params={'login': ','.join(usernames)})
        users = r.json()['users']
        existing_usernames = {user['name'] for user in users}
        # Existing usernames
        ids = [(user['name'], user['_id']) for user in users]
        # Missing usernames
        ids.extend([(username, None) for username in usernames if username not in existing_usernames])
        return ids

    def _request_get(self, path: str, domain: Optional[str] = None, params: Optional[Dict] = None) -> requests.Response:
        if not domain:
            url = urljoin(f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/', path)
        else:
            url = urljoin(domain, path)
        r = self._fetch(url, params, headers=self.headers)
        return r


class TwitchAPIError(Exception):
    pass


class InvalidStreamQuality(TwitchAPIError, StopIteration):
    pass


class NonexistentChannel(TwitchAPIError):
    pass


class NoValidVideo(TwitchAPIError):
    pass
