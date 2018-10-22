import re
from abc import ABCMeta, abstractmethod
from datetime import timedelta
from typing import Iterator, List, Optional, Tuple, Union, cast

from iso8601 import parse_date

from .base import BaseAPI, CloseableAsyncContextManager, TwitchAPIError
from .data import StreamInfo, TwitchVideo
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
    async def get_videos(self, channel: str, video_type: str = 'archive', *,
                         limit: Union[str, int] = 100) -> List[TwitchVideo]:
        """returns list of 100 last videos from last channel sorted by time
        :param channel: channel name
        :param video_type: possible values {'all', 'archive', 'highlight', 'upload'}
        :param limit: number of videos to fetch, possible 'all'
        """
        if not (isinstance(limit, int) or limit == 'all'):
            raise ValueError('Invalid limit value. Possible: int or `all`')
        return []

    @abstractmethod
    async def get_video(self, video_id: str) -> TwitchVideo:
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
                          started_at=parse_date(data['created_at']),
                          data=data)

    async def get_videos(self, channel: str, video_type: str = 'archive', *,
                         limit: Union[str, int] = TwitchAPIv5.MAX_LIMIT) -> List[TwitchVideo]:
        await super().get_videos(channel, video_type, limit=limit)

        if video_type == 'all':
            video_type = ''
        user_id = await self._get_user_id(channel)

        videos: List[TwitchVideo] = []
        number_of_videos = None if isinstance(limit, str) else limit
        for offset, n in offset_generator(number_of_videos, part_size=TwitchAPIv5.MAX_LIMIT):
            data = await self._api.get_channel_videos(user_id, offset=offset, limit=n, broadcast_type=[video_type])
            if not data['videos']:
                break
            videos.extend(TwitchVideo(video_id=video['_id'],
                                      title=video['title'],
                                      video_type=video['broadcast_type'],
                                      channel_name=video['channel']['name'],
                                      created_at=parse_date(video['created_at']),
                                      duration=int(video['length']),
                                      data=video)
                          for video in data['videos'])
        return videos

    async def get_video(self, video_id: str) -> TwitchVideo:
        video = await self._api.get_video(video_id.lstrip('v'))
        return TwitchVideo(video_id=video['_id'],
                           title=video['title'],
                           video_type=video['broadcast_type'],
                           channel_name=video['channel']['name'],
                           created_at=parse_date(video['created_at']),
                           duration=int(video['length']),
                           data=video)

    async def get_streams(self, channels: List[str], *, stream_type: str = 'live') -> List[StreamInfo]:
        user_ids = [user['_id'] for user in await self._api.get_users(channels)]
        data_list = (await self._api.get_live_streams(channel=user_ids))['streams']
        if not data_list:
            return []
        return [StreamInfo(channel_name=data['channel']['name'],
                           channel_id=data['channel']['_id'],
                           game=data['game'],
                           status=data['channel']['status'],
                           started_at=parse_date(data['created_at']),
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

    async def get_videos(self, channel: str, video_type: str = 'archive', *,
                         limit: Union[str, int] = TwitchAPIHelix.MAX_IDS) -> List[TwitchVideo]:
        await super().get_videos(channel, video_type, limit=limit)

        user_id = await self._get_user_id(channel)

        videos: List[TwitchVideo] = []
        number_of_videos = None if isinstance(limit, str) else limit
        cursor = None
        for _, n in offset_generator(number_of_videos, part_size=TwitchAPIHelix.MAX_IDS):
            data = await self._api.get_videos(user_id=user_id, first=n, type=video_type, after=cursor)
            cursor = data.cursor
            if not data.data:
                break
            videos.extend(TwitchVideo(video_id=video_info['id'],
                                      title=video_info['title'],
                                      video_type=video_info['type'],
                                      channel_name=channel,
                                      created_at=parse_date(video_info['created_at']),
                                      duration=parse_duration(video_info['duration']),
                                      data=video_info)
                          for video_info in data.data)
        return videos

    async def get_video(self, video_id: str) -> TwitchVideo:
        helix_data = await self._api.get_videos(id=[video_id])
        video_info = helix_data.data[0]
        user = (await self._api.get_users(id=[video_info['user_id']]))[0]
        return TwitchVideo(video_id=video_info['id'],
                           title=video_info['title'],
                           video_type=video_info['type'],
                           channel_name=user['login'],
                           created_at=parse_date(video_info['created_at']),
                           duration=parse_duration(video_info['duration']),
                           data=video_info)

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
                               started_at=parse_date(stream['started_at']),
                               data=stream)
                    for stream in stream_data.data]
    return stream_infos if len(stream_infos) > 1 else stream_infos[0]


def offset_generator(limit: Optional[int], part_size: int) -> Iterator[Tuple[int, int]]:
    offset = 0
    if limit:
        remaining = limit
        while remaining > 0:
            n = part_size if remaining > part_size else remaining
            yield offset, n
            remaining -= part_size
            offset += part_size
    else:
        while True:
            yield offset, part_size
            offset += part_size


def parse_duration(string: str) -> int:
    duration_re = re.compile(r'(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?')
    duration_match = duration_re.fullmatch(string)
    if not duration_match or not any(duration_match.groupdict()):
        raise ValueError(f'Duration string "{string}" can not be parsed into duration')
    return timedelta(**{k: int(v) for k, v in duration_match.groupdict().items() if v}).seconds
