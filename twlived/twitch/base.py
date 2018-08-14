from typing import Any, Collection, Dict, List, Mapping, Optional, Tuple, Union

import requests
from requests.exceptions import ChunkedEncodingError, HTTPError

from ..utils import retry_on_exception

JSONT = Dict[str, Any]
URLParameterT = Union[List[Tuple[str, str]], Mapping[str, Optional[Union[str, Collection[str]]]]]
ResponseT = requests.Response

retry_api = retry_on_exception((HTTPError, ChunkedEncodingError), wait=2, max_tries=10)


class BaseAPI:
    def __init__(self, *, retry: bool = False) -> None:
        self._session = requests.Session()
        self._id_storage: Dict[str, Dict[str, Any]] = {}
        self._login_storage: Dict[str, Dict[str, Any]] = {}
        self.retry = retry

    def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        if self.retry:
            return retry_api(self._raw_request)(method, url, params=params)
        else:
            return self._raw_request(method, url, params=params)

    def _raw_request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        # Remove parameters which can not be converted uniquely to string
        filtered_params = params
        if isinstance(params, dict):
            filtered_params = filter_none_and_empty(params)
            if filtered_params:
                filtered_params = {name: ','.join(value) if isinstance(value, list) else value
                                   for name, value in filtered_params.items()}

        # Seems like a mistake in requests *.stub definitions. You can pass List[Tuple[str, str]] as params also.
        response = self._session.request(method, url, params=filtered_params, timeout=20)  # type: ignore

        self._handle_response(response)
        response.raise_for_status()

        return response

    def _handle_response(self, response: ResponseT) -> None:
        pass


def filter_none_and_empty(dictionary: Dict[Any, Any]) -> Dict[Any, Any]:
    return {key: value for key, value in dictionary.items() if value}


def bool_to_str(value: bool) -> str:
    return 'true' if value else 'false'


class TwitchAPIError(Exception):
    pass
