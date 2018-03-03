import functools
import json
from itertools import chain
from time import time as utc, time
from typing import Dict, List, Callable, Tuple, Any, Optional, Union, TypeVar
from urllib.parse import urljoin

import requests

from .config_logging import log

log = log.getChild('TwitchAPI')

RF = Callable[..., requests.Response]
T = TypeVar('T')


def timed_cache(func: Callable[..., Dict]) -> Callable[..., Dict]:
    cache: Dict[str, Tuple[Dict, int]] = {}

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Dict:
        _, video_id, *_ = args
        if video_id not in cache or cache[video_id][1] < utc():
            token = func(*args, **kwargs)
            cache[video_id] = token, json.loads(token['token'])['expires']
        return cache[video_id][0]

    return wrapper


def filter_none_and_empty(dictionary: Dict) -> Dict:
    return {key: value for key, value in dictionary.items() if value}


def identity(obj: T) -> T:
    return obj


class TwitchAPI:
    """Class implementing part of Twitch API Helix."""

    OFFICIAL_API: str = 'https://api.twitch.tv/helix/'
    TOKEN_DOMAIN: str = 'https://api.twitch.tv/api/'
    USHER_DOMAIN: str = 'https://usher.ttvnw.net/'
    MAX_IDS: int = 100
    STREAM_TYPES = {'all', 'live', 'vodcast'}
    PERIODS = {'all', 'day', 'month', 'week'}
    SORT_VALUES = {'time', 'trending', 'views'}
    VIDEO_TYPES = {'all', 'upload', 'archive', 'highlight'}
    HUB_MODES = {'subscribe', 'unsubscribe'}
    headers: Dict[str, str] = {'Content-Type': 'application/json'}

    def __init__(self, client_id: str, *, request_wrapper: Callable[[RF], RF] = identity) -> None:
        self.headers.update({'Client-ID': client_id})
        self._wrap_requests(request_wrapper)
        self._id_storage: Dict[str, Dict] = {}
        self._login_storage: Dict[str, Dict] = {}
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._ratelimit_remaining = 30
        self._ratelimit_reset: Union[int, float] = time()

    # noinspection PyShadowingBuiltins
    def get_streams(self, *,
                    after: Optional[str] = None,
                    before: Optional[str] = None,
                    community_id: Optional[List[str]] = None,
                    first: int = 20,
                    game_id: Optional[List[str]] = None,
                    language: Optional[List[str]] = None,
                    type: str = 'all',
                    user_id: Optional[List[str]] = None,
                    user_login: Optional[List[str]] = None) -> Tuple[List[Dict], Optional[str]]:
        limited_size_args = {
            'community_id': len(community_id) if community_id is not None else 0,
            'game_id': len(game_id) if game_id is not None else 0,
            'language': len(language) if language is not None else 0,
            'user_id': len(user_id) if user_id is not None else 0,
            'user_login': len(user_login) if user_login is not None else 0,
        }
        for arg, value in limited_size_args.items():
            if value > TwitchAPI.MAX_IDS:
                raise ValueError(f'You can specify up to {TwitchAPI.MAX_IDS} IDs for {arg}')
        if first > TwitchAPI.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to 100')
        if type not in TwitchAPI.STREAM_TYPES:
            raise ValueError(f'Invalid value for stream type. Valid values: {TwitchAPI.STREAM_TYPES}')
        if after and before:
            raise ValueError('Provide only one pagination direction.')
        params: Dict[str, Union[str, List[str]]] = filter_none_and_empty({
            'after': after,
            'before': before,
            'community_id': community_id,
            'first': str(first),
            'game_id': game_id,
            'language': language,
            'type': type,
            'user_id': user_id,
            'user_login': user_login,
        })
        response = self._helix_get('streams', params=params)
        return response['data'], response['pagination']['cursor'] if response['pagination'] else None

    # noinspection PyShadowingBuiltins
    def get_videos(self, *,
                   id: Optional[List[str]] = None,
                   user_id: Optional[str] = None,
                   game_id: Optional[str] = None,
                   after: Optional[str] = None,
                   before: Optional[str] = None,
                   first: int = 20,
                   language: Optional[str] = None,
                   period: str = 'all',
                   sort: str = 'time',
                   type: str = 'all') -> Tuple[List[Dict], Optional[str]]:
        num_args = sum(map(lambda x: int(x is not None), [id, user_id, game_id]))
        if num_args == 0:
            raise ValueError('Must provide one of the arguments: list of id, user_id, game_id')
        if num_args > 1:
            raise ValueError('Must provide only one of the arguments: list of id, user_id, game_id')
        if id and len(id) > TwitchAPI.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPI.MAX_IDS} IDs')
        if after and before:
            raise ValueError('Provide only one pagination direction.')
        if first > TwitchAPI.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPI.MAX_IDS}')
        if period not in TwitchAPI.PERIODS:
            raise ValueError(f'Invalid value for period. Valid values: {TwitchAPI.PERIODS}')
        if sort not in TwitchAPI.SORT_VALUES:
            raise ValueError(f'Invalid value for sort. Valid values: {TwitchAPI.SORT_VALUES}')
        if type not in TwitchAPI.VIDEO_TYPES:
            raise ValueError(f'Invalid value for type of video. Valid values: {TwitchAPI.VIDEO_TYPES}')
        params: Dict[str, Union[str, List[str]]] = filter_none_and_empty({
            'id': id,
            'user_id': user_id,
            'game_id': game_id,
            'after': after,
            'before': before,
            'first': str(first),
            'language': language,
            'period': period,
            'sort': sort,
            'type': type,
        })
        response = self._helix_get('videos', params=params)
        return response['data'], response['pagination']['cursor'] if response['pagination'] else None

    # noinspection PyShadowingBuiltins
    def get_users(self, *,
                  id: Optional[List[str]] = None,
                  login: Optional[List[str]] = None,
                  retrieve_new: bool = False) -> List[Dict[str, Union[str, int]]]:
        if not (id or login):
            raise ValueError('Specify one argument list of IDs or list of logins')
        if id and len(id) > TwitchAPI.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPI.MAX_IDS} IDs')
        if login and len(login) > TwitchAPI.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPI.MAX_IDS} logins')
        id, login = id or [], login or []
        if retrieve_new:
            missing_ids, missing_logins = id, login
        else:
            missing_ids = list(filter(lambda x: x not in self._id_storage, id or []))
            missing_logins = list(filter(lambda x: x not in self._login_storage, login or []))
        params: Dict[str, Union[str, List[str]]] = filter_none_and_empty({
            'id': missing_ids,
            'login': missing_logins,
        })
        if params:
            response = self._helix_get('users', params=params)
            for user in response['data']:
                self._id_storage[user['id']] = user
                self._login_storage[user['login']] = user

        return list(user for user in chain((self._id_storage.get(id_, None) for id_ in set(id)),
                                           (self._login_storage.get(login_, None) for login_ in set(login)))
                    if user is not None)

    @timed_cache
    def get_video_token(self, video_id: str) -> Dict:
        response: Dict = self._get(f'{TwitchAPI.TOKEN_DOMAIN}vods/{video_id}/access_token',
                                   params={'need_https': 'true'},
                                   headers=self.headers).json()
        return response

    def get_variant_playlist(self, video_id: str) -> str:
        token = self.get_video_token(video_id)
        return self._get(f'{TwitchAPI.USHER_DOMAIN}vod/{video_id}',
                         params={
                             'nauthsig': token['sig'],
                             'nauth': token['token'],
                             'allow_source': 'true',
                             'allow_audio_only': 'true',
                         }).text

    def get_channel_token(self, login: str) -> Dict:
        response: Dict = self._get(f'{TwitchAPI.TOKEN_DOMAIN}channels/{login}/access_token',
                                   params={'need_https': 'true'},
                                   headers=self.headers).json()
        return response

    def get_live_variant_playlist(self, login: str) -> str:
        token = self.get_channel_token(login)
        return self._get(f'{TwitchAPI.USHER_DOMAIN}api/channel/hls/{login}.m3u8',
                         params={'token': token['token'],
                                 'sig': token['sig'],
                                 'allow_source': 'true'}).text

    def post_webhook(self, hub_callback: str, hub_mode: str, hub_topic: 'HubTopic', *,
                     hub_lease_seconds: int = 864000,
                     hub_secret: str = '') -> None:
        if hub_mode not in TwitchAPI.HUB_MODES:
            raise ValueError(f'Invalid hub.mode. Valid values: {TwitchAPI.HUB_MODES}')
        params = {
            'hub.callback': hub_callback,
            'hub.mode': hub_mode,
            'hub.topic': hub_topic,
            'hub.lease_seconds': str(hub_lease_seconds),
            'hub.secret': hub_secret,
        }
        self._helix_post('webhooks/hub', params=params)

    def _request(self, method: str, url: str, *,
                 params: Optional[Dict] = None) -> requests.Response:
        if not self._ratelimit_remaining and self._ratelimit_reset > time():
            raise RateLimitOverflow(f'Wait {self._ratelimit_reset} until the limit is reset')
        response = self._session.request(method, url, params=params)
        ratelimit_remaining = response.headers.get('Ratelimit-Remaining', None)
        ratelimit_reset = response.headers.get('Ratelimit-Reset', None)
        self._ratelimit_remaining = int(ratelimit_remaining) if ratelimit_remaining else self._ratelimit_remaining
        self._ratelimit_reset = int(ratelimit_reset) if ratelimit_reset else self._ratelimit_reset
        response.raise_for_status()
        return response

    @staticmethod
    def _get(url: str, *,
             params: Optional[Dict] = None,
             headers: Optional[Dict[str, str]] = None) -> requests.Response:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response

    def _helix_get(self, path: str, *, params: Optional[Dict] = None) -> Dict:
        return self._request('get', urljoin(TwitchAPI.OFFICIAL_API, path), params=params).json()

    def _helix_post(self, path: str, *, params: Optional[Dict] = None) -> requests.Response:
        return self._request('post', urljoin(TwitchAPI.OFFICIAL_API, path), params=params)

    def _wrap_requests(self, request_wrapper):
        self._request = request_wrapper(self._request)
        self._get = request_wrapper(self._request)


class HubTopic(str):
    @classmethod
    def follows(cls, from_id: str = '', to_id: str = ''):
        if not (from_id or to_id):
            raise ValueError('Specify at least one argument from_id or to_id')
        params = ''
        params += f'from_id={from_id}' if from_id else ''
        params += f'from_id={to_id}' if to_id else ''
        return cls(urljoin(TwitchAPI.OFFICIAL_API, f'users/follows?{params}'))

    @classmethod
    def streams(cls, user_id: str):
        return cls(urljoin(TwitchAPI.OFFICIAL_API, f'streams?user_id={user_id}'))


class TwitchAPIError(Exception):
    pass


class RateLimitOverflow(TwitchAPIError):
    pass
