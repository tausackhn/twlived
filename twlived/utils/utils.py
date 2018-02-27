import functools
import operator
from collections import deque
from itertools import repeat
from time import sleep
from typing import List, Tuple, Callable, Any, Generator, TypeVar, Iterator, Union, Type, Optional

FT = Callable[..., Any]
T = TypeVar('T')


def retry_on_exception(exceptions: Union[Type[Exception], Tuple[Type[Exception]]],
                       wait: float = 2,
                       max_tries: int = Optional[None]) -> Callable[[FT], FT]:
    def decorator(f: FT) -> FT:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tries = 0
            while True:
                tries += 1
                try:
                    # noinspection PyCallingNonCallable
                    result = f(*args, **kwargs)
                except exceptions:
                    if tries == max_tries:
                        raise
                    sleep(wait)
                else:
                    return result

        return wrapper

    return decorator


def chunked(l: List[T], chunk_size: int) -> Iterator[List[T]]:
    for i in range(0, len(l), chunk_size):
        yield l[i:i + chunk_size]


def sanitize_filename(filename: str, replace_to: str = '') -> str:
    excepted_chars = list(r':;/\?|*<>.')
    for char in excepted_chars:
        filename = filename.replace(char, replace_to)
    return filename


def fails_in_row(num: int) -> Generator[bool, bool, None]:
    buffer = deque(repeat(True, num), maxlen=num)
    while True:
        new_value = yield functools.reduce(operator.ior, buffer)
        if new_value is not None:
            buffer.append(new_value)
