from abc import ABCMeta, abstractmethod
from typing import List, Optional, Union, cast

from .base import BaseAPI, CloseableAsyncContextManager, JSONT, TwitchAPIError
from .data import StreamInfo
from .helix import HelixData, TwitchAPIHelix
from .v5 import TwitchAPIv5


class TwitchAPIAdapter(CloseableAsyncContextManager, metaclass=ABCMeta):
    def __init__(self, client_id: str, *, client_secret: Optional[str] = None, retry: bool = False) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def closed(self) -> bool:
        return self.api.closed

    @property
    @abstractmethod
    def api(self) -> BaseAPI:
        """returns API object"""

    @abstractmethod
    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[StreamInfo]:
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

    @abstractmethod
    async def get_streams(self, channels: List[str], *, stream_type: str = 'live') -> List[StreamInfo]:
        """returns streams by list of channel names
        :param channels: list of channel names
        :param stream_type: possible values {'live', 'playlist', 'premiere', 'rerun'}
        """

    async def close(self) -> None:
        if not self.api.closed:
            await self.api.close()


class TwitchAPIv5Adapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, client_secret: Optional[str] = None, retry: bool = False) -> None:
        super().__init__(client_id, client_secret=client_secret, retry=retry)
        self._api = TwitchAPIv5(client_id, retry=retry)

    @property
    def api(self) -> BaseAPI:
        return self._api

    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[StreamInfo]:
        user_id = await self._get_user_id(channel)
        data = (await self._api.get_stream(user_id, stream_type=stream_type))['stream']
        if not data:
            return None
        return StreamInfo(channel_name=data['channel']['name'],
                          channel_id=data['channel']['_id'],
                          game=data['game'],
                          status=data['channel']['status'],
                          data=data)

    async def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        if video_type == 'all':
            video_type = ''
        user_id = await self._get_user_id(channel)
        data = await self._api.get_channel_videos(user_id, limit=100, broadcast_type=[video_type])
        return cast(List[JSONT], data['videos'])

    async def get_video(self, video_id: str) -> JSONT:
        return await self._api.get_video(video_id.lstrip('v'))

    async def get_streams(self, channels: List[str], *, stream_type: str = 'live') -> List[StreamInfo]:
        user_ids = list(map(lambda u: u['_id'], await self._api.get_users(channels)))
        data_list = (await self._api.get_live_streams(channel=user_ids))['streams']
        if not data_list:
            return []
        return [StreamInfo(channel_name=data['channel']['name'],
                           channel_id=data['channel']['_id'],
                           game=data['game'],
                           status=data['channel']['status'],
                           data=data)
                for data in data_list]

    async def _get_user_id(self, channel: str) -> str:
        try:
            data = await self._api.get_users([channel])
            return cast(str, data[0]['_id'])
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc


class TwitchAPIHelixAdapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, client_secret: Optional[str] = None, retry: bool = False) -> None:
        super().__init__(client_id, client_secret=client_secret, retry=retry)
        self._api = TwitchAPIHelix(client_id, client_secret=client_secret, retry=retry)

    @property
    def api(self) -> BaseAPI:
        return self._api

    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[StreamInfo]:
        user_id = await self._get_user_id(channel)
        stream_data = await self._api.get_streams(user_id=[user_id])
        if not stream_data.data or stream_data.data[0]['type'] != stream_type:
            return None

        return cast(StreamInfo, await prepare_stream_info(self._api, stream_data))

    async def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        user_id = await self._get_user_id(channel)
        data = await self._api.get_videos(user_id=user_id, first=100, type=video_type)
        return data[0]

    async def get_video(self, video_id: str) -> JSONT:
        data = await self._api.get_videos(id=[video_id])
        return data[0][0]

    async def get_streams(self, channels: List[str], *, stream_type: str = 'live') -> List[StreamInfo]:
        streams_data = await self._api.get_streams(user_login=channels, first=TwitchAPIHelix.MAX_IDS)
        prepared_info = await prepare_stream_info(self._api, streams_data)
        if not isinstance(prepared_info, list):
            prepared_info = [prepared_info]
        return list(filter(lambda s: s.data['type'] == stream_type, prepared_info))

    async def _get_user_id(self, channel: str) -> str:
        try:
            data = await self._api.get_users(login=[channel])
            return cast(str, data[0]['id'])
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc


async def prepare_stream_info(helix_api: TwitchAPIHelix, stream_data: HelixData) -> Union[StreamInfo, List[StreamInfo]]:
    user_ids = {user['user_id'] for user in stream_data.data}
    game_ids = {user['game_id'] for user in stream_data.data}
    if not user_ids:
        return []

    user_data = await helix_api.get_users(id=list(user_ids))
    game_data = await helix_api.get_games(id=list(game_ids))

    games = {game['id']: game['name'] for game in game_data}
    users = {user['id']: user['login'] for user in user_data}

    stream_infos = [StreamInfo(channel_name=users[stream['user_id']],
                               channel_id=stream['user_id'],
                               game=games[stream['game_id']],
                               status=stream['title'],
                               data=stream)
                    for stream in stream_data.data]
    return stream_infos if len(stream_infos) > 1 else stream_infos[0]
