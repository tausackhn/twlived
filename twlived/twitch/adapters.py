from abc import ABCMeta, abstractmethod
from typing import List, Optional

from .base import BaseAPI, JSONT, TwitchAPIError
from .helix import TwitchAPIHelix
from .v5 import TwitchAPIv5


class TwitchAPIAdapter(BaseAPI, metaclass=ABCMeta):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(retry=retry)
        self.client_id = client_id
        self.headers = {'Client-ID': client_id}

    @abstractmethod
    def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        """returns stream by channel name
        :param channel: channel name
        :param stream_type: possible values {'live', 'playlist', 'premiere', 'rerun'}
        """

    @abstractmethod
    def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        """returns list of 100 last videos from last channel sorted by time
        :param channel: channel name
        :param video_type: possible values {'all', 'archive', 'highlight', 'upload'}
        """

    @abstractmethod
    def get_video(self, video_id: str) -> JSONT:
        """returns video info by video_id
        :param video_id: number with or without `v`
        """


class TwitchAPIv5Adapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(client_id, retry=retry)
        self._api = TwitchAPIv5(client_id, retry=retry)

    def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        user_id = self._get_user_id(channel)
        return self._api.get_stream(user_id, stream_type=stream_type)['stream']

    def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        if video_type == 'all':
            video_type = ''
        user_id = self._get_user_id(channel)
        return self._api.get_channel_videos(user_id, limit=100, broadcast_type=video_type)['videos']

    def get_video(self, video_id: str) -> JSONT:
        return self._api.get_video(video_id.lstrip('v'))

    def _get_user_id(self, channel: str) -> str:
        try:
            return self._api.get_users([channel])[0]['_id']
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc


class TwitchAPIHelixAdapter(TwitchAPIAdapter):
    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(client_id, retry=retry)
        self._api = TwitchAPIHelix(client_id, retry=retry)

    def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        user_id = self._get_user_id(channel)
        stream_info = self._api.get_streams(user_id=[user_id])[0][0]
        if stream_info['type'] != stream_type:
            return None
        return stream_info

    def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        user_id = self._get_user_id(channel)
        return self._api.get_videos(user_id=user_id, first=100, type=video_type)[0]

    def get_video(self, video_id: str) -> JSONT:
        return self._api.get_videos(id=[video_id])[0][0]

    def _get_user_id(self, channel: str) -> str:
        try:
            return self._api.get_users(login=[channel])[0]['id']
        except IndexError as exc:
            raise TwitchAPIError(f'Channel {channel} did not found on twitch.tv') from exc
