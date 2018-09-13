import json
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urljoin

from .base import BaseAPI, JSONT, ResponseT, URLParameterT


def timed_cache(func: Callable[..., Any]) -> Callable[..., Any]:
    cache: Dict[str, Tuple[Dict[str, Any], int]] = {}

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        _, video_id, *_ = args
        if video_id not in cache or cache[video_id][1] < time.time():
            token = await func(*args, **kwargs)
            cache[video_id] = token, json.loads(token['token'])['expires']
        return cache[video_id][0]

    return wrapper


def no_headers(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        self, *_ = args
        headers = self._headers
        self._headers = {}
        return_value = await func(*args, **kwargs)
        self._headers = headers
        return return_value

    return wrapper


class TwitchAPIHidden(BaseAPI):
    TOKEN_DOMAIN: str = 'https://api.twitch.tv/api/'
    USHER_DOMAIN: str = 'https://usher.ttvnw.net/'

    def __init__(self, client_id: str) -> None:
        super().__init__()
        self.client_id = client_id

    @timed_cache
    async def get_video_token(self, video_id: str) -> JSONT:
        return await self._get_api(f'vods/{video_id}/access_token', params={'need_https': 'true'})

    @timed_cache
    async def get_channel_token(self, login: str) -> JSONT:
        return await self._get_api(f'channels/{login}/access_token', params={'need_https': 'true'})

    @no_headers
    async def get_variant_playlist(self, video_id: str) -> str:
        token = await self.get_video_token(video_id)
        return await self._get_usher(f'vod/{video_id}',
                                     params={
                                         'nauthsig':         token['sig'],
                                         'nauth':            token['token'],
                                         'allow_source':     'true',
                                         'allow_audio_only': 'true',
                                     })

    @no_headers
    async def get_live_variant_playlist(self, channel: str) -> str:
        token = await self.get_channel_token(channel)
        return await self._get_usher(f'api/channel/hls/{channel}.m3u8',
                                     params={
                                         'token':        token['token'],
                                         'sig':          token['sig'],
                                         'allow_source': 'true',
                                     })

    @no_headers
    async def get_channel_badges(self, channel_id: str):
        # https://badges.twitch.tv/v1/badges/channels/<channel_id>/display
        response = await self._request('get', f'https://badges.twitch.tv/v1/badges/channels/{channel_id}/display')
        return await response.json()

    async def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        self._headers.update({'Client-ID': self.client_id})
        return await super()._request(method, url, params=params)

    async def _get_api(self, path: str, *, params: Optional[URLParameterT] = None) -> JSONT:
        response = await self._request('get', urljoin(TwitchAPIHidden.TOKEN_DOMAIN, path), params=params)
        return await response.json()

    async def _get_usher(self, path: str, *, params: Optional[URLParameterT] = None) -> str:
        response = await self._request('get', urljoin(TwitchAPIHidden.USHER_DOMAIN, path), params=params)
        return await response.text()
