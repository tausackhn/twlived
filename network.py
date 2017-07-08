# coding=utf-8
from typing import Any

import requests
from requests.exceptions import HTTPError, ConnectionError, ChunkedEncodingError, Timeout
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on


@retry(retry=(retry_on(HTTPError) | retry_on(ConnectionError) | retry_on(Timeout) | retry_on(ChunkedEncodingError)),
       wait=wait_fixed(5),
       stop=stop_after_attempt(30),
       reraise=True)
def request_get_retried(*args: Any, **kwargs: Any) -> requests.Response:
    r = requests.get(timeout=30, *args, **kwargs)
    r.raise_for_status()
    return r
