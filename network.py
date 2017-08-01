from typing import Any

import requests
# pylint: disable=redefined-builtin
from requests.exceptions import HTTPError, ConnectionError, ChunkedEncodingError, Timeout
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on


@retry(retry=(retry_on(HTTPError) | retry_on(ConnectionError) | retry_on(Timeout) | retry_on(ChunkedEncodingError)),
       wait=wait_fixed(5),
       stop=stop_after_attempt(30),
       reraise=True)
def request_get_retried(*args: Any, **kwargs: Any) -> requests.Response:
    request = requests.get(timeout=30, *args, **kwargs)
    request.raise_for_status()
    return request
