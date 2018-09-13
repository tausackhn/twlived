import asyncio
import functools
import operator
from collections import deque
from itertools import repeat
from typing import Any, Awaitable, Callable, Generator, Iterator, List, Optional, Type, TypeVar

CoroT = Callable[..., Awaitable[Any]]
T = TypeVar('T')


def retry_on_exception(*exceptions: Type[Exception],
                       wait: float = 2,
                       max_tries: Optional[int] = None) -> Callable[[CoroT], CoroT]:
    def decorator(f: CoroT) -> CoroT:
        @functools.wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tries = 0
            while True:
                tries += 1
                try:
                    result = await f(*args, **kwargs)
                except tuple(exceptions):
                    if tries == max_tries:
                        raise
                    await asyncio.sleep(wait)
                else:
                    return result

        return wrapper

    return decorator


def all_subclasses(klass: Type[T]) -> Iterator[Type[T]]:
    subclasses = klass.__subclasses__()
    for subclass in subclasses:
        yield subclass
    for subclass in subclasses:
        yield from all_subclasses(subclass)


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
