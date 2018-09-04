from functools import wraps
from itertools import chain
from time import time
from typing import Any, Callable, List, Optional, Tuple, Union
from urllib.parse import urljoin

from .base import BaseAPI, JSONT, ResponseT, TwitchAPIError, URLParameterT

HelixDataT = Tuple[List[JSONT], Optional[str]]


def require_app_token(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        self, *_ = args
        if not self.client_secret:
            raise TwitchAPIError('Requires client_secret')
        return func(*args, **kwargs)

    return wrapper


class TwitchAPIHelix(BaseAPI):
    """Class implementing part of Twitch API Helix."""

    DOMAIN: str = 'https://api.twitch.tv/helix/'
    MAX_IDS: int = 100
    STREAM_TYPES = {'all', 'live', 'vodcast'}
    PERIODS = {'all', 'day', 'month', 'week'}
    SORT_VALUES = {'time', 'trending', 'views'}
    VIDEO_TYPES = {'all', 'upload', 'archive', 'highlight'}
    HUB_MODES = {'subscribe', 'unsubscribe'}

    def __init__(self, client_id: str, *, client_secret: Optional[str] = None, retry: bool = False) -> None:
        super().__init__(retry=retry)
        self._headers.update({'Client-ID': client_id})

        self.client_secret = client_secret

        # Without Bearer Token
        self._ratelimit_remaining = 30
        self._ratelimit_reset: Union[int, float] = time()

    # noinspection PyShadowingBuiltins
    async def get_streams(self, *,
                          after: Optional[str] = None,
                          before: Optional[str] = None,
                          community_id: Optional[List[str]] = None,
                          first: int = 20,
                          game_id: Optional[List[str]] = None,
                          language: Optional[List[str]] = None,
                          user_id: Optional[List[str]] = None,
                          user_login: Optional[List[str]] = None) -> HelixDataT:
        limited_size_args = {
            'community_id': len(community_id) if community_id is not None else 0,
            'game_id':      len(game_id) if game_id is not None else 0,
            'language':     len(language) if language is not None else 0,
            'user_id':      len(user_id) if user_id is not None else 0,
            'user_login':   len(user_login) if user_login is not None else 0,
        }

        for arg, value in limited_size_args.items():
            if value > TwitchAPIHelix.MAX_IDS:
                raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs for {arg}')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to 100')
        if type not in TwitchAPIHelix.STREAM_TYPES:
            raise ValueError(f'Invalid value for stream type. Valid values: {TwitchAPIHelix.STREAM_TYPES}')
        if after and before:
            raise ValueError('Provide only one pagination direction.')

        params = {
            'after':        after,
            'before':       before,
            'community_id': community_id,
            'first':        str(first),
            'game_id':      game_id,
            'language':     language,
            'user_id':      user_id,
            'user_login':   user_login,
        }

        response = await self._helix_get('streams', params=params)
        return self._extract_helix_data(response)

    # noinspection PyShadowingBuiltins
    async def get_videos(self, *,
                         id: Optional[List[str]] = None,
                         user_id: Optional[str] = None,
                         game_id: Optional[str] = None,
                         after: Optional[str] = None,
                         before: Optional[str] = None,
                         first: int = 20,
                         language: Optional[str] = None,
                         period: str = 'all',
                         sort: str = 'time',
                         type: str = 'all') -> HelixDataT:
        num_args = sum(map(lambda x: int(x is not None), [id, user_id, game_id]))
        if num_args == 0:
            raise ValueError('Must provide one of the arguments: list of id, user_id, game_id')
        if num_args > 1:
            raise ValueError('Must provide only one of the arguments: list of id, user_id, game_id')
        if id and len(id) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs')
        if after and before:
            raise ValueError('Provide only one pagination direction.')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPIHelix.MAX_IDS}')
        if period not in TwitchAPIHelix.PERIODS:
            raise ValueError(f'Invalid value for period. Valid values: {TwitchAPIHelix.PERIODS}')
        if sort not in TwitchAPIHelix.SORT_VALUES:
            raise ValueError(f'Invalid value for sort. Valid values: {TwitchAPIHelix.SORT_VALUES}')
        if type not in TwitchAPIHelix.VIDEO_TYPES:
            raise ValueError(f'Invalid value for type of video. Valid values: {TwitchAPIHelix.VIDEO_TYPES}')

        params = {
            'id':       id,
            'user_id':  user_id,
            'game_id':  game_id,
            'after':    after,
            'before':   before,
            'first':    str(first),
            'language': language,
            'period':   period,
            'sort':     sort,
            'type':     type,
        }

        response = await self._helix_get('videos', params=params)
        return self._extract_helix_data(response)

    # noinspection PyShadowingBuiltins
    async def get_users(self, *,
                        id: Optional[List[str]] = None,
                        login: Optional[List[str]] = None,
                        update_storage: bool = False) -> List[JSONT]:
        if not (id or login):
            raise ValueError('Specify one argument list of IDs or list of logins')
        if id and len(id) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs')
        if login and len(login) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} logins')

        id, login = id or [], login or []

        if not update_storage:
            missing_ids = filter(lambda x: x not in self._id_storage, id)
            missing_logins = filter(lambda x: x not in self._login_storage, login)
        else:
            missing_ids, missing_logins = iter(id), iter(login)

        params = [('id', id_) for id_ in missing_ids] + [('login', login_) for login_ in missing_logins]

        if params:
            response = await self._helix_get('users', params=params)
            data = response['data']
            for user in data:
                self._id_storage[user['id']] = self._login_storage[user['login']] = user

        return list(user for user in chain((self._id_storage.get(id_, None) for id_ in set(id)),
                                           (self._login_storage.get(login_, None) for login_ in set(login)))
                    if user is not None)

    # noinspection PyShadowingBuiltins
    async def get_clips(self, *,
                        broadcaster_id: Optional[str] = None,
                        game_id: Optional[str] = None,
                        id: Optional[List[str]] = None,
                        after: Optional[str] = None,
                        before: Optional[str] = None,
                        first: int = 20) -> HelixDataT:
        num_args = sum(map(lambda x: int(x is not None), [broadcaster_id, game_id, id]))
        if num_args == 0:
            raise ValueError('Must provide one of the arguments: list of id, broadcaster_id, game_id')
        if num_args > 1:
            raise ValueError('Must provide only one of the arguments: list of id, broadcaster_id, game_id')
        if id and len(id) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs')
        if after and before:
            raise ValueError('Provide only one pagination direction.')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPIHelix.MAX_IDS}')

        params = {
            'broadcaster_id': broadcaster_id,
            'game_id':        game_id,
            'id':             id,
            'after':          after,
            'before':         before,
            'first':          str(first)
        }

        response = await self._helix_get('clips', params=params)
        return self._extract_helix_data(response)

    # noinspection PyShadowingBuiltins
    async def get_games(self, *,
                        id: Optional[List[str]] = None,
                        name: Optional[str] = None) -> List[JSONT]:
        num_args = sum(map(lambda x: int(x is not None), [id, name]))
        if num_args == 0:
            raise ValueError('Must provide one of the arguments: list of id, name')
        if num_args > 1:
            raise ValueError('Must provide only one of the arguments: list of id, name')
        if id and len(id) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs')

        params = {
            'id':   id,
            'name': name
        }

        response = await self._helix_get('games', params=params)
        data, _ = self._extract_helix_data(response)
        return data

    async def get_top_games(self, *,
                            after: Optional[str] = None,
                            before: Optional[str] = None,
                            first: int = 20) -> HelixDataT:
        if after and before:
            raise ValueError('Provide only one pagination direction.')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPIHelix.MAX_IDS}')

        params = {
            'after':  after,
            'before': before,
            'first':  str(first)
        }

        response = await self._helix_get('games/top', params=params)
        return self._extract_helix_data(response)

    async def get_streams_metadata(self, *,
                                   after: Optional[str] = None,
                                   before: Optional[str] = None,
                                   community_id: Optional[List[str]] = None,
                                   first: int = 20,
                                   game_id: Optional[List[str]] = None,
                                   language: Optional[List[str]] = None,
                                   user_id: Optional[List[str]] = None,
                                   user_login: Optional[List[str]] = None) -> HelixDataT:
        limited_size_args = {
            'community_id': len(community_id) if community_id is not None else 0,
            'game_id':      len(game_id) if game_id is not None else 0,
            'language':     len(language) if language is not None else 0,
            'user_id':      len(user_id) if user_id is not None else 0,
            'user_login':   len(user_login) if user_login is not None else 0,
        }

        for arg, value in limited_size_args.items():
            if value > TwitchAPIHelix.MAX_IDS:
                raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs for {arg}')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to 100')
        if type not in TwitchAPIHelix.STREAM_TYPES:
            raise ValueError(f'Invalid value for stream type. Valid values: {TwitchAPIHelix.STREAM_TYPES}')
        if after and before:
            raise ValueError('Provide only one pagination direction.')

        params = {
            'after':        after,
            'before':       before,
            'community_id': community_id,
            'first':        str(first),
            'game_id':      game_id,
            'language':     language,
            'user_id':      user_id,
            'user_login':   user_login,
        }

        # TODO: Handle global rate limit
        # Headers:
        # Ratelimit-Helixstreamsmetadata-Limit: <int value>
        # Ratelimit-Helixstreamsmetadata-Remaining: <int value>
        response = await self._helix_get('streams/metadata', params=params)
        return self._extract_helix_data(response)

    async def get_users_follows(self, *,
                                after: Optional[str] = None,
                                first: int = 20,
                                from_id: Optional[str] = None,
                                to_id: Optional[str] = None):
        if not (from_id or to_id):
            raise ValueError('At minimum, from_id or to_id must be provided')
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPIHelix.MAX_IDS}')

        params = {
            'after':   after,
            'first':   str(first),
            'from_id': from_id,
            'to_id':   to_id
        }

        response = await self._helix_get('users/follows', params=params)
        return self._extract_helix_data(response)

    @require_app_token
    async def get_webhook_subscriptions(self, *,
                                        after: Optional[str] = None,
                                        first: int = 20):
        if first > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'The value of the first must be less than or equal to {TwitchAPIHelix.MAX_IDS}')

        params = {
            'after': after,
            'first': str(first)
        }

        response = await self._helix_get('webhooks/subscriptions', params=params)
        return self._extract_helix_data(response)

    async def post_webhook(self, hub_callback: str, hub_mode: str, hub_topic: 'HubTopic', *,
                           hub_lease_seconds: int = 864000,
                           hub_secret: str = '') -> None:
        if hub_mode not in TwitchAPIHelix.HUB_MODES:
            raise ValueError(f'Invalid hub.mode. Valid values: {TwitchAPIHelix.HUB_MODES}')

        params = {
            'hub.callback':      hub_callback,
            'hub.mode':          hub_mode,
            'hub.topic':         hub_topic,
            'hub.lease_seconds': str(hub_lease_seconds),
            'hub.secret':        hub_secret,
        }

        await self._helix_post('webhooks/hub', params=params)

    async def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        if not self._ratelimit_remaining and self._ratelimit_reset > time():
            raise RateLimitOverflow(f'Wait {self._ratelimit_reset} until the limit is reset')

        response = await super()._request(method, url, params=params)
        await self._handle_response(response)
        return response

    async def _handle_response(self, response: ResponseT) -> None:
        ratelimit_remaining = response.headers.get('Ratelimit-Remaining', None)
        ratelimit_reset = response.headers.get('Ratelimit-Reset', None)
        if ratelimit_remaining and ratelimit_reset:
            self._ratelimit_remaining = int(ratelimit_remaining)
            self._ratelimit_reset = int(ratelimit_reset)

    async def _helix_get(self, path: str, *, params: Optional[URLParameterT] = None) -> JSONT:
        response = await self._request('get', urljoin(TwitchAPIHelix.DOMAIN, path), params=params)
        print(response.status)
        return await response.json()

    async def _helix_post(self, path: str, *, params: Optional[URLParameterT] = None) -> str:
        response = await self._request('post', urljoin(TwitchAPIHelix.DOMAIN, path), params=params)
        return await response.text()

    @staticmethod
    def _extract_helix_data(response: JSONT) -> HelixDataT:
        return response['data'], response['pagination']['cursor'] if response['pagination'] else None


class HubTopic(str):
    @classmethod
    def follows(cls, from_id: str = '', to_id: str = '') -> str:
        if not (from_id or to_id):
            raise ValueError('Specify at least one argument from_id or to_id')
        params = ''
        params += f'from_id={from_id}' if from_id else ''
        params += f'from_id={to_id}' if to_id else ''
        return cls(urljoin(TwitchAPIHelix.DOMAIN, f'users/follows?{params}'))

    @classmethod
    def streams(cls, user_id: str) -> str:
        return cls(urljoin(TwitchAPIHelix.DOMAIN, f'streams?user_id={user_id}'))


class RateLimitOverflow(TwitchAPIError):
    pass
