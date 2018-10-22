from typing import Dict, List, Optional, Type, Union

from .adapters import TwitchAPIAdapter, TwitchAPIHelixAdapter, TwitchAPIv5Adapter
from .base import BaseAPI, TwitchAPIError
from .data import StreamInfo, TwitchVideo
from .hidden import TwitchAPIHidden


class TwitchAPI(TwitchAPIAdapter):
    API_ADAPTERS: Dict[str, Type[TwitchAPIAdapter]] = {
        'v5':    TwitchAPIv5Adapter,
        'Helix': TwitchAPIHelixAdapter,
    }
    VERSIONS = set(API_ADAPTERS.keys())

    def __init__(self, client_id: str, *,
                 client_secret: Optional[str] = None,
                 retry: bool = False,
                 version: str = 'v5') -> None:
        super().__init__(client_id, client_secret=client_secret, retry=retry)
        self._version = version
        self.version = version
        self._api_adapters = {name: Adapter(client_id, client_secret=client_secret) for name, Adapter in
                              TwitchAPI.API_ADAPTERS.items()}
        self._hidden_api = TwitchAPIHidden(client_id)

    @property
    def closed(self) -> bool:
        return all(adapter.closed for adapter in self._api_adapters.values()) and self._hidden_api.closed

    @property
    def api(self) -> BaseAPI:
        return self._api_adapters[self.version].api

    @property
    def _adapter(self) -> TwitchAPIAdapter:
        return self._api_adapters[self.version]

    @property
    def version(self) -> str:
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        if version not in TwitchAPI.VERSIONS:
            raise TwitchAPIError(f'Unknown TwitchAPI version: {version}. Possible values {TwitchAPI.VERSIONS}')
        self._version = version

    def get_api(self, version: str) -> BaseAPI:
        if version not in TwitchAPI.VERSIONS:
            raise TwitchAPIError(f'Unknown TwitchAPI version: {version}. Possible values {TwitchAPI.VERSIONS}')
        return self._api_adapters[version].api

    async def get_stream(self, channel: str, *, stream_type: str = 'live') -> Optional[StreamInfo]:
        return await self._adapter.get_stream(channel, stream_type=stream_type)

    async def get_videos(self, channel: str, video_type: str = 'archive', *,
                         limit: Union[str, int] = 100) -> List[TwitchVideo]:
        return await self._adapter.get_videos(channel, video_type=video_type, limit=limit)

    async def get_video(self, video_id: str) -> TwitchVideo:
        return await self._adapter.get_video(video_id)

    async def get_streams(self, channels: List[str], *, stream_type: str = 'live') -> List[StreamInfo]:
        return await self._adapter.get_streams(channels, stream_type=stream_type)

    async def get_variant_playlist(self, video_id: str) -> str:
        return await self._hidden_api.get_variant_playlist(video_id.lstrip('v'))

    async def get_live_variant_playlist(self, channel: str) -> str:
        return await self._hidden_api.get_live_variant_playlist(channel)

    async def close(self) -> None:
        for adapter in self._api_adapters.values():
            await adapter.close()
        await self._hidden_api.close()
