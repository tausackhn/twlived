import functools
import json
from time import time as utc
from typing import Dict, List, Callable, Tuple, Any, TypeVar, Optional
from urllib.parse import urljoin

import requests

from .config_logging import log
from .utils import method_dispatch

log = log.getChild('TwitchAPI')

T = TypeVar('T')


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

    API_DOMAIN: str = 'https://api.twitch.tv'
    KRAKEN: str = '/kraken'
    API: str = '/api'
    USHER_DOMAIN: str = 'https://usher.ttvnw.net'
    MAX_VIDEOS: int = 100
    DEFAULT_NUM_VIDEOS: int = 10
    MAX_IDS: int = 100
    headers: Dict[str, str] = {'Accept': 'application/vnd.twitchtv.v5+json'}

    def __init__(self, client_id: str, *, request_wrapper: Optional[Callable[[T], T]] = None) -> None:
        self.headers.update({'Client-ID': client_id})
        self._request_wrapper = request_wrapper
        # Take unbound method. Make an usual function using partial()
        # issue: https://github.com/python/mypy/issues/1484
        self._get_user_id = self._UserIDStorage(functools.partial(TwitchAPI._get_user_id_, self))  # type: ignore

    def update_id_storage(self, channels: List[str]) -> None:
        self._get_user_id(channels)

    def get_stream(self, channel: str) -> Dict:
        log.debug(f'Retrieving stream status: {channel}')
        channel_id = self._get_user_id(channel)
        request = self.__kraken_get(f'streams/{channel_id}')
        return request.json()

    def get_stream_status(self, channel: str) -> str:
        streams = self.get_streams(channels=[channel])
        live_stream = streams['_total'] > 0 and streams['streams'][0]['stream_type'] == 'live'
        return 'online' if live_stream else 'offline'

    def get_streams(self, *,
                    channels: Optional[List[str]] = None,
                    game: Optional[str] = None,
                    language: Optional[str] = None,
                    stream_type: Optional[str] = None,
                    limit: int = 25, offset: int = 0) -> Dict:
        if isinstance(channels, list):
            log.debug(f'Retrieving streams info: {len(channels)} {channels}')
        else:
            log.debug(f'Retrieving streams info: {game}, {language}, {stream_type}, {limit}, {offset}')
        if limit > 100:
            raise TwitchAPIError('Too much streams requested. Must be <= 100')
        channel_ids = self._get_user_id(channels) if channels else None
        if channel_ids and None in channel_ids:
            raise NonexistentChannel(f'Some channels in {channels} are not exist')
        params = {'channel': ','.join(channel_ids) if channel_ids else None,
                  'game': game,
                  'language': language,
                  'stream_type': stream_type,
                  'limit': str(limit),
                  'offset': str(offset)}
        params = {key: value for key, value in params.items() if value}
        request = self.__kraken_get('streams', params=params)
        return request.json()

    def get_videos(self, channel: str, *, broadcast_type: str = 'archive', require_all: bool = False) -> List[Dict]:
        log.debug(f'Retrieving videos: {channel} {broadcast_type} require_all={require_all}')
        channel_id = self._get_user_id(channel)
        offset = 0
        limit = TwitchAPI.MAX_VIDEOS if require_all else TwitchAPI.DEFAULT_NUM_VIDEOS
        videos: List[Dict] = []

        while True:
            request = self.__kraken_get(f'channels/{channel_id}/videos',
                                        params={'broadcast_type': broadcast_type,
                                                'offset': str(offset),
                                                'limit': str(limit)})
            videos.extend(request.json()['videos'])
            if not require_all or not request.json()['videos']:
                break
            offset += TwitchAPI.MAX_VIDEOS

        return videos

    def get_video(self, id_: str) -> Dict:
        log.debug(f'Retrieving video: {id_}')
        request = self.__kraken_get(f'videos/{id_}')
        return request.json()

    def get_channel_info(self, channel: str) -> Dict:
        log.debug(f'Retrieving channel info: {channel}')
        channel_id = self._get_user_id(channel)
        if channel_id:
            request = self.__kraken_get(f'channels/{channel_id}')
            return request.json()
        else:
            raise NonexistentChannel(channel)

    def get_recording_videos(self, channel: str) -> List[Dict]:
        log.debug(f'Retrieving recording video: {channel}')
        last_broadcasts = self.get_videos(channel)
        recording_videos = [broadcast for broadcast in last_broadcasts if broadcast['status'] == 'recording']
        if not recording_videos:
            raise NoValidVideo(f'No recording video at {channel}')
        return recording_videos

    @token_storage
    def _get_token(self, vod_id: str) -> Dict:
        log.debug(f'Retrieving token: {vod_id}')
        request = self.__api_get(f'vods/{vod_id}/access_token', params={'need_https': 'true'})
        return request.json()

    def get_variant_playlist(self, vod_id: str) -> str:
        vod_id = vod_id.lstrip('v')
        token = self._get_token(vod_id)
        log.debug(f'Retrieving variant playlist: {vod_id} {token}')
        request = self.__get(f'vod/{vod_id}', domain=TwitchAPI.USHER_DOMAIN,
                             params={'nauthsig': token['sig'],
                                     'nauth': token['token'],
                                     'allow_source': 'true',
                                     'allow_audio_only': 'true'})
        return request.text

    class _UserIDStorage:
        """
        Class, which caches {username: user ID} for API methods.
        Saves one request, when one uses method by username.
        """
        cache: Dict[str, Optional[str]] = {}

        def __init__(self, get_items: Callable[[List[str]], List[Tuple[str, Optional[str]]]]) -> None:
            self._get_items = get_items

        @method_dispatch
        def __call__(self, _: Any) -> Any:
            raise ValueError

        # issue: https://github.com/python/mypy/issues/708
        @__call__.register(str)  # type: ignore
        def _str(self, username: str) -> str:
            return self([username])[0]

        # issue: https://github.com/python/mypy/issues/708
        @__call__.register(list)  # type: ignore
        def _list(self, usernames: List[str]) -> List[Optional[str]]:
            log.debug(f'Retrieving user-id from IDStorage: {len(usernames)} {usernames}')
            missing_names = [_ for _ in usernames if _ not in self.cache]
            if missing_names:
                self._update(missing_names)
            return [self.cache[username] for username in usernames]

        def _update(self, items: List[str]) -> None:
            log.debug(f'Updating user-id: {len(items)} {items}')
            max_id = TwitchAPI.MAX_IDS
            items_chunks = [items[i:i + max_id] for i in range(0, len(items), max_id)]
            for chunk in items_chunks:
                ids = self._get_items(chunk)
                self.cache.update(ids)

    def _get_user_id_(self, usernames: List[str]) -> List[Tuple[str, Optional[str]]]:
        log.debug(f'Retrieving user-id: {len(usernames)} {usernames}')
        if len(usernames) > TwitchAPI.MAX_IDS:
            raise TwitchAPIError('Too much usernames. Must be <= 100')
        request = self.__kraken_get('users', params={'login': ','.join(usernames)})
        users = request.json()['users']
        existing_usernames = {user['name'] for user in users}
        # Existing usernames
        ids = [(user['name'], user['_id']) for user in users]
        # Missing usernames
        ids.extend([(username, None) for username in usernames if username not in existing_usernames])
        return ids

    def __get(self, path: str, domain: str, *, params: Optional[Dict] = None) -> requests.Response:
        url = urljoin(domain, path)
        if self._request_wrapper is not None:
            get_url = self._request_wrapper(requests.get)
        else:
            get_url = requests.get
        request = get_url(url, params, headers=self.headers)
        return request

    def __kraken_get(self, path: str, *, params: Optional[Dict[str, str]] = None) -> requests.Response:
        return self.__get(path, domain=f'{TwitchAPI.API_DOMAIN}{TwitchAPI.KRAKEN}/', params=params)

    def __api_get(self, path: str, *, params: Optional[Dict[str, str]] = None) -> requests.Response:
        return self.__get(path, domain=f'{TwitchAPI.API_DOMAIN}{TwitchAPI.API}/', params=params)


class TwitchAPIError(Exception):
    pass


class InvalidStreamQuality(TwitchAPIError, StopIteration):
    pass


class NonexistentChannel(TwitchAPIError):
    pass


class NoValidVideo(TwitchAPIError):
    pass
