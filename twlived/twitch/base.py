import asyncio
from abc import ABCMeta, abstractmethod
from types import TracebackType
from typing import Any, AsyncContextManager, Collection, Dict, Iterator, Mapping, Optional, Tuple, Type, Union

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
from multidict import MultiDict

JSONT = Dict[str, Any]
URLParameterT = Union[
    Collection[Tuple[str, Optional[str]]],
    Mapping[str, Optional[str]],
]
ResponseT = aiohttp.ClientResponse


class CloseableAsyncContextManager(AsyncContextManager, metaclass=ABCMeta):
    async def __aexit__(self, exc_type: Optional[Type[BaseException]],
                        exc_val: Optional[BaseException],
                        exc_tb: Optional[TracebackType]) -> Optional[bool]:
        await self.close()
        return None

    @abstractmethod
    async def close(self) -> None:
        pass

    @property
    @abstractmethod
    def closed(self) -> bool:
        pass


class BaseAPI(CloseableAsyncContextManager):
    def __init__(self, *, retry: bool = False) -> None:
        self._session = aiohttp.ClientSession(raise_for_status=True,
                                              timeout=aiohttp.client.ClientTimeout(sock_connect=30,
                                                                                   total=60))
        self._id_storage: Dict[str, Dict[str, Any]] = {}
        self._login_storage: Dict[str, Dict[str, Any]] = {}
        self.retry = retry
        self._headers: Dict[str, str] = {}

    @property
    def closed(self) -> bool:
        return self._session.closed

    async def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        def backoff_delay() -> Iterator[int]:
            base = 2
            i = 1
            while True:
                yield base ** i
                i += 1

        delay = backoff_delay()

        while True:
            try:
                return await self._raw_request(method, url, params=params)
            except ClientResponseError as e:
                if e.status == 429:
                    sleep_time = next(delay)
                    await asyncio.sleep(sleep_time)
                else:
                    raise

    async def _raw_request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        filtered_params: MultiDict[str]
        if params:
            params = MultiDict(params)
            # Remove empty and None values
            filtered_params = MultiDict((key, value) for key, value in params.items() if value)
        else:
            filtered_params = MultiDict()
        return await self._session.request(method, url, params=filtered_params, headers=self._headers)

    async def close(self) -> None:
        if not self.closed:
            await self._session.close()


def bool_to_str(value: bool) -> str:
    return 'true' if value else 'false'


class TwitchAPIError(Exception):
    pass
