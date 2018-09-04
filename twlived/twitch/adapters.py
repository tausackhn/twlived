from abc import ABCMeta, abstractmethod
from typing import List, Optional

from .base import BaseAPI, JSONT, TwitchAPIError
from .helix import TwitchAPIHelix
from .v5 import TwitchAPIv5


class TwitchAPIAdapter(metaclass=ABCMeta):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        self.client_id = client_id

    @property
    @abstractmethod
    def api(self) -> BaseAPI:
        """returns API object"""

    @abstractmethod
    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        """returns stream by channel name
        :param channel: channel name
        :param stream_type: possible values {'live', 'playlist', 'premiere', 'rerun'}
        """

    @abstractmethod
    async def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        """returns list of 100 last videos from last channel sorted by time
        :param channel: channel name
        :param video_type: possible values {'all', 'archive', 'highlight', 'upload'}
        """

    @abstractmethod
    async def get_video(self, video_id: str) -> JSONT:
        """returns video info by video_id
        :param video_id: number with or without `v`
        """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if not self.api.closed:
            await self.api.close()


class TwitchAPIv5Adapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(client_id, retry=retry)
        self._api = TwitchAPIv5(client_id, retry=retry)

    @property
    def api(self) -> BaseAPI:
        return self._api

    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        user_id = await self._get_user_id(channel)
        data = await self._api.get_stream(user_id, stream_type=stream_type)
        return data['stream']

    async def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        if video_type == 'all':
            video_type = ''
        user_id = await self._get_user_id(channel)
        data = await self._api.get_channel_videos(user_id, limit=100, broadcast_type=video_type)
        return data['videos']

    async def get_video(self, video_id: str) -> JSONT:
        return await self._api.get_video(video_id.lstrip('v'))

    async def _get_user_id(self, channel: str) -> str:
        try:
            data = await self._api.get_users([channel])
            return data[0]['_id']
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc


class TwitchAPIHelixAdapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(client_id, retry=retry)
        self._api = TwitchAPIHelix(client_id, retry=retry)

    @property
    def api(self) -> BaseAPI:
        return self._api

    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        user_id = await self._get_user_id(channel)
        data = await self._api.get_streams(user_id=[user_id])
        stream_info = data[0][0]
        if stream_info['type'] != stream_type:
            return None
        return stream_info

    async def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        user_id = await self._get_user_id(channel)
        data = await self._api.get_videos(user_id=user_id, first=100, type=video_type)
        return data[0]

    async def get_video(self, video_id: str) -> JSONT:
        data = await self._api.get_videos(id=[video_id])
        return data[0][0]

    async def _get_user_id(self, channel: str) -> str:
        try:
            data = await self._api.get_users(login=[channel])
            return data[0]['id']
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc
