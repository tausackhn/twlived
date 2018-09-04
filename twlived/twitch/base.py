from typing import Any, Collection, Dict, List, Mapping, Optional, Tuple, Union

import aiohttp

JSONT = Dict[str, Any]
URLParameterT = Union[List[Tuple[str, str]], Mapping[str, Optional[Union[str, Collection[str]]]]]
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
        filtered_params = params
        if isinstance(params, dict):
            filtered_params = filter_none_and_empty(params)
            if filtered_params:
                filtered_params = {name: ','.join(value) if isinstance(value, list) else value
                                   for name, value in filtered_params.items()}

        return await self._session.request(method, url, params=filtered_params, headers=self._headers)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if not self.closed:
            await self._session.close()


def filter_none_and_empty(dictionary: Dict[Any, Any]) -> Dict[Any, Any]:
    return {key: value for key, value in dictionary.items() if value}


def bool_to_str(value: bool) -> str:
    return 'true' if value else 'false'


class TwitchAPIError(Exception):
    pass
