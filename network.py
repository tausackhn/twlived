# coding=utf-8
import requests
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on


@retry(retry=(retry_on(requests.HTTPError) | retry_on(requests.ConnectionError)),
       wait=wait_fixed(5),
       stop=stop_after_attempt(30))
def request_get_retried(*args, **kwargs):
    r = requests.get(*args, **kwargs)
    r.raise_for_status()
    return r
