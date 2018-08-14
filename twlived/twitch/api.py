from typing import Dict, List, Optional, Type

from .adapters import TwitchAPIAdapter, TwitchAPIHelixAdapter, TwitchAPIv5Adapter
from .base import JSONT, TwitchAPIError
from .hidden import TwitchAPIHidden


class TwitchAPI(TwitchAPIAdapter):
    API_ADAPTERS: Dict[str, Type[TwitchAPIAdapter]] = {
        'v5':    TwitchAPIv5Adapter,
        'Helix': TwitchAPIHelixAdapter,
    }
    VERSIONS = set(API_ADAPTERS.keys())

    def __init__(self, client_id: str, *, retry: bool = False, version: str = 'v5') -> None:
        super().__init__(client_id, retry=retry)
        self._version = version
        self.version = version
        self._api_adapters = {name: Adapter(client_id) for name, Adapter in TwitchAPI.API_ADAPTERS.items()}
        self._hidden_api = TwitchAPIHidden(client_id)

    @property
    def _api(self) -> TwitchAPIAdapter:
        return self._api_adapters[self.version]

    @property
    def version(self) -> str:
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        if version not in TwitchAPI.VERSIONS:
            raise TwitchAPIError(f'Unknown TwitchAPI version: {version}. Possible values {TwitchAPI.VERSIONS}')
        self._version = version

    def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[JSONT]:
        return self._api.get_stream(channel, stream_type=stream_type)

    def get_videos(self, channel: str, video_type: str = 'archive') -> List[JSONT]:
        return self._api.get_videos(channel, video_type=video_type)

    def get_video(self, video_id: str) -> JSONT:
        return self._api.get_video(video_id)

    def get_variant_playlist(self, video_id: str) -> str:
        return self._hidden_api.get_variant_playlist(video_id)

    def get_live_variant_playlist(self, channel: str) -> str:
        return self._hidden_api.get_live_variant_playlist(channel)
