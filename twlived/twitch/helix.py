from functools import wraps
from itertools import chain
from time import time
from typing import Any, Callable, List, NamedTuple, Optional, Tuple, Union
from urllib.parse import urljoin

import aiohttp

from .base import BaseAPI, JSONT, ResponseT, TwitchAPIError, URLParameterT


class HelixData(NamedTuple):
    data: List[JSONT]
    cursor: Optional[str]

    @classmethod
    def from_json(cls, data: JSONT):
        if 'pagination' in data:
            cursor = data['pagination']['cursor'] if data['pagination'] else None
        else:
            cursor = None
        return cls(data['data'], cursor)


class AccessToken(NamedTuple):
    access_token: str
    expires: Union[float, int]


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
    APP_TOKEN_URL: str = 'https://id.twitch.tv/oauth2/token'
    MAX_IDS: int = 100
    STREAM_TYPES = {'all', 'live', 'vodcast'}
    PERIODS = {'all', 'day', 'month', 'week'}
    SORT_VALUES = {'time', 'trending', 'views'}
    VIDEO_TYPES = {'all', 'upload', 'archive', 'highlight'}
    HUB_MODES = {'subscribe', 'unsubscribe'}

    def __init__(self, client_id: str, *, client_secret: Optional[str] = None, retry: bool = False) -> None:
        super().__init__(retry=retry)

        self.client_secret = client_secret
        self.client_id = client_id
        self._app_access_token: Optional[AccessToken] = None

        if not self.client_secret:
            # Without Bearer Token
            self._ratelimit_remaining = 30
        else:
            # Authorization header will be set
            self._ratelimit_remaining = 120
        self._ratelimit_reset: Union[int, float] = time()

    @property
    async def access_token(self):
        if not self.client_secret:
            raise TwitchAPIError('Requires client_secret')
        if (self.client_secret and not self._app_access_token) or self._app_access_token.expires > time():
            await self.authorize()
        return self._app_access_token.access_token

    # noinspection PyShadowingBuiltins
    async def get_streams(self, *,
                          after: Optional[str] = None,
                          before: Optional[str] = None,
                          community_id: Optional[List[str]] = None,
                          first: int = 20,
                          game_id: Optional[List[str]] = None,
                          language: Optional[List[str]] = None,
                          user_id: Optional[List[str]] = None,
                          user_login: Optional[List[str]] = None) -> HelixData:
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
        if after and before:
            raise ValueError('Provide only one pagination direction.')

        params: List[Tuple[str, Optional[str]]] = [
            ('after', after),
            ('before', before),
            ('first', str(first)),
        ]
        params += [('community_id', community_id_) for community_id_ in community_id or []]
        params += [('user_id', user_id_) for user_id_ in user_id or []]
        params += [('user_login', user_login_) for user_login_ in user_login or []]
        params += [('game_id', game_id_) for game_id_ in game_id or []]
        params += [('language', language_) for language_ in language or []]

        response = await self._helix_get('streams', params=params)
        return HelixData.from_json(response)

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
                         type: str = 'all') -> HelixData:
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

        params = [
            ('user_id', user_id),
            ('game_id', game_id),
            ('after', after),
            ('before', before),
            ('first', str(first)),
            ('language', language),
            ('period', period),
            ('sort', sort),
            ('type', type),
        ]
        params += [('id', id_) for id_ in id or []]

        response = await self._helix_get('videos', params=params)
        return HelixData.from_json(response)

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
                        first: int = 20) -> HelixData:
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

        params = [
            ('broadcaster_id', broadcaster_id),
            ('game_id', game_id),
            ('after', after),
            ('before', before),
            ('first', str(first))
        ]
        params += [('id', id_) for id_ in id or []]

        response = await self._helix_get('clips', params=params)
        return HelixData.from_json(response)

    # noinspection PyShadowingBuiltins
    async def get_games(self, *,
                        id: Optional[List[str]] = None,
                        name: Optional[List[str]] = None) -> List[JSONT]:
        num_args = sum(map(lambda x: int(x is not None), [id, name]))
        if num_args == 0:
            raise ValueError('Must provide one of the arguments: list of id, name')
        if num_args > 1:
            raise ValueError('Must provide only one of the arguments: list of id, name')
        if id and len(id) > TwitchAPIHelix.MAX_IDS:
            raise ValueError(f'You can specify up to {TwitchAPIHelix.MAX_IDS} IDs')

        params = [('id', id_) for id_ in id or []] + [('name', name_) for name_ in name or []]

        response = await self._helix_get('games', params=params)
        return response['data']

    async def get_top_games(self, *,
                            after: Optional[str] = None,
                            before: Optional[str] = None,
                            first: int = 20) -> HelixData:
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
        return HelixData.from_json(response)

    async def get_streams_metadata(self, *,
                                   after: Optional[str] = None,
                                   before: Optional[str] = None,
                                   community_id: Optional[List[str]] = None,
                                   first: int = 20,
                                   game_id: Optional[List[str]] = None,
                                   language: Optional[List[str]] = None,
                                   user_id: Optional[List[str]] = None,
                                   user_login: Optional[List[str]] = None) -> HelixData:
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
        if after and before:
            raise ValueError('Provide only one pagination direction.')

        params = [
            ('after', after),
            ('before', before),
            ('first', str(first)),
        ]
        params += [('community_id', community_id_) for community_id_ in community_id or []]
        params += [('user_id', user_id_) for user_id_ in user_id or []]
        params += [('user_login', user_login_) for user_login_ in user_login or []]
        params += [('game_id', game_id_) for game_id_ in game_id or []]
        params += [('language', language_) for language_ in language or []]
        # TODO: Handle global rate limit
        # Headers:
        # Ratelimit-Helixstreamsmetadata-Limit: <int value>
        # Ratelimit-Helixstreamsmetadata-Remaining: <int value>
        response = await self._helix_get('streams/metadata', params=params)
        return HelixData.from_json(response)

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
        return HelixData.from_json(response)

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
        return HelixData.from_json(response)

    async def post_webhook(self, hub_callback: str, hub_mode: str, hub_topic: str, *,
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

    @require_app_token
    async def authorize(self):
        params = {
            'client_id':     self.client_id,
            'client_secret': self.client_secret,
            'grant_type':    'client_credentials'
        }
        response = await (await super()._request('post', TwitchAPIHelix.APP_TOKEN_URL, params=params)).json()
        self._app_access_token = AccessToken(access_token=response['access_token'],
                                             expires=time() + response['expires_in'] - 1)

    async def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        # Prefer authorized client due to higher rate limit
        if self.client_secret:
            # TODO: remove when typed-ast would support Python 3.7 (https://github.com/python/typed_ast/issues/60)
            access_token = await self.access_token
            self._headers.update({'Authorization': f'Bearer {access_token}'})
        else:
            self._headers.update({'Client-ID': self.client_id})

        if not self._ratelimit_remaining and self._ratelimit_reset > time():
            raise RateLimitOverflow(f'Wait {self._ratelimit_reset} until the limit is reset')

        tries = 0
        # Auto-authorization flow. Trying to request first time and
        # trying to authorize and request again if authorization revoked.
        while tries < 2:
            try:
                tries += 1
                response = await super()._request(method, url, params=params)
            except aiohttp.ClientResponseError as e:
                # Twitch revoked Bearer token.
                if e.status == 401 and self.client_secret and tries < 2:
                    # Trying to authorize once again.
                    # Could raise exception if the client secret is invalid.
                    await self.authorize()
                else:
                    raise
            else:
                await self._handle_response(response)
                return response

        raise Exception('Should never reach this point')

    async def _handle_response(self, response: ResponseT) -> None:
        ratelimit_remaining = 30 if not self.client_secret else 120
        ratelimit_remaining = response.headers.get('Ratelimit-Remaining', None) or ratelimit_remaining
        ratelimit_reset = response.headers.get('Ratelimit-Reset', None) or time()
        if ratelimit_remaining and ratelimit_reset:
            self._ratelimit_remaining = int(ratelimit_remaining)
            self._ratelimit_reset = int(ratelimit_reset)

    async def _helix_get(self, path: str, *, params: Optional[URLParameterT] = None) -> JSONT:
        response = await self._request('get', urljoin(TwitchAPIHelix.DOMAIN, path), params=params)
        return await response.json()

    async def _helix_post(self, path: str, *, params: Optional[URLParameterT] = None) -> str:
        response = await self._request('post', urljoin(TwitchAPIHelix.DOMAIN, path), params=params)
        return await response.text()


class HubTopic(str):
    @classmethod
    def follows(cls, from_id: str = '', to_id: str = '') -> str:
        if not (from_id or to_id):
            raise ValueError('Specify at least one argument from_id or to_id')
        params = 'first=1'
        params += f'&from_id={from_id}' if from_id else ''
        params += f'&to_id={to_id}' if to_id else ''
        return cls(urljoin(TwitchAPIHelix.DOMAIN, f'users/follows?{params}'))

    @classmethod
    def streams(cls, user_id: str) -> str:
        return cls(urljoin(TwitchAPIHelix.DOMAIN, f'streams?user_id={user_id}'))


class RateLimitOverflow(TwitchAPIError):
    pass
