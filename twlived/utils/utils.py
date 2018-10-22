import asyncio
import functools
import logging
import operator
from collections import deque
from contextlib import suppress
from itertools import repeat
from typing import (Any, Awaitable, Callable, Generator, Iterable, Iterator, List, Optional, Set, Type, TypeVar,
                    get_type_hints, no_type_check)

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


def task_group(coro: Callable[[T], Awaitable[None]], args_list: Iterable[Iterable[T]]) -> List[asyncio.Task]:
    def callback(t: asyncio.Task) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.warning('Got an exception in group tasks {coro_name} over {args_list}:',
                            exc_info=True,
                            extra={'coro_name': coro.__name__, 'args_list': args_list})
            raise

    tasks = []
    for args in args_list:
        task = asyncio.create_task(coro(*args))
        task.add_done_callback(callback)
        tasks.append(task)

    return tasks


async def wait_group(tasks: List[asyncio.Task]) -> Set[asyncio.Future]:
    _, task_for_cancel = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    group_for_cancel = asyncio.gather(*task_for_cancel, return_exceptions=True)
    group_for_cancel.cancel()
    with suppress(asyncio.CancelledError):
        await group_for_cancel

    return task_for_cancel


@no_type_check
def methoddispatch(method):
    dispatcher = functools.singledispatch(method)

    def register(method_):
        _, klass_ = next(iter(get_type_hints(method_).items()))
        return dispatcher.register(klass_)(method_)

    def dispatch(klass):
        return dispatcher.dispatch(klass)

    def wrapper(instance, dispatch_data, *args, **kwargs):
        klass = type(dispatch_data)
        implementation = dispatch(klass)
        return implementation(instance, dispatch_data, *args, **kwargs)

    wrapper.register = register
    wrapper.dispatch = dispatch
    wrapper.registry = dispatcher.registry
    wrapper._clear_cache = dispatcher._clear_cache
    functools.update_wrapper(wrapper, method)

    return wrapper
