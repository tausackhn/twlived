import functools
import json
from itertools import chain
from time import time as utc
from typing import Dict, List, Callable, Tuple, Any, Optional, Union

import requests
from mypy_extensions import DefaultNamedArg

from .config_logging import log

log = log.getChild('TwitchAPI')

RF = Callable[[str, DefaultNamedArg(Optional[Dict], 'params'),
               DefaultNamedArg(Optional[Dict[str, str]], 'headers')], requests.Response]


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
    headers: Dict[str, str] = {'Content-Type': 'application/json'}

    def __init__(self, client_id: str, *, request_wrapper: Optional[Callable[[RF], RF]] = None) -> None:
        self.headers.update({'Client-ID': client_id})
        self._request_wrapper = request_wrapper
        self._id_storage: Dict[str, Dict] = {}
        self._login_storage: Dict[str, Dict] = {}

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
        response = self._helix_get('streams', params=params).json()
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
        response = self._helix_get('videos', params=params).json()
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
            response = self._helix_get('users', params=params).json()
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

    @staticmethod
    def __get(url: str, *,
              params: Optional[Dict] = None,
              headers: Optional[Dict[str, str]] = None) -> requests.Response:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        # TODO: support Rate Limits https://dev.twitch.tv/docs/api#rate-limits
        return response

    def _get(self, url: str, *,
             params: Optional[Dict] = None,
             headers: Optional[Dict[str, str]] = None) -> requests.Response:
        if self._request_wrapper is not None:
            get_url = self._request_wrapper(self.__get)
        else:
            get_url = self.__get
        response = get_url(url, params=params, headers=headers)
        return response

    def _helix_get(self, path: str, *, params: Optional[Dict[str, Union[str, List[str]]]] = None) -> requests.Response:
        return self._get(TwitchAPI.OFFICIAL_API + path, params=params, headers=self.headers)
