from typing import Any, Collection, Dict, Mapping, Optional, Tuple, Union, overload

import aiohttp

JSONT = Dict[str, Any]
URLParameterT = Union[Collection[Tuple[str, Optional[str]]], Mapping[str, Union[str, Collection[str], None]]]
ResponseT = aiohttp.ClientResponse


class BaseAPI:
    def __init__(self, *, retry: bool = False) -> None:
        self._session = aiohttp.ClientSession(raise_for_status=True,
                                              timeout=aiohttp.client.ClientTimeout(sock_connect=10,
                                                                                   total=20))
        self._id_storage: Dict[str, Dict[str, Any]] = {}
        self._login_storage: Dict[str, Dict[str, Any]] = {}
        self.retry = retry
        self._headers: Dict[str, str] = {}

    @property
    def closed(self):
        return self._session.closed

    async def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        return await self._raw_request(method, url, params=params)

    async def _raw_request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        # Remove parameters which can not be converted uniquely to string
        if params:
            filtered_params = filter_none_and_empty(params)
            if isinstance(filtered_params, Mapping):
                filtered_params = {name: ','.join(value) if isinstance(value, list) else value
                                   for name, value in filtered_params.items()}
        else:
            filtered_params = {}

        return await self._session.request(method, url, params=filtered_params, headers=self._headers)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if not self.closed:
            await self._session.close()


@overload
def filter_none_and_empty(d: Collection[Tuple[Any, Any]]) -> Collection[Tuple[Any, Any]]: ...


@overload
def filter_none_and_empty(d: Mapping[Any, Any]) -> Mapping[Any, Any]: ...


def filter_none_and_empty(d: Union[Collection[Tuple[Any, Any]], Mapping[Any, Any]]) \
        -> Union[Collection[Tuple[Any, Any]], Mapping[Any, Any]]:
    if isinstance(d, Mapping):
        return {key: value for key, value in d.items() if value}
    else:
        return [(key, value) for key, value in d if value]


def bool_to_str(value: bool) -> str:
    return 'true' if value else 'false'


class TwitchAPIError(Exception):
    pass
