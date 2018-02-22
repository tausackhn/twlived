import functools
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


def split_by(l: List[T], element: T) -> Tuple[List[T], List[T]]:
    try:
        element_index = l.index(element)
        return l[:element_index], l[element_index + 1:]
    except ValueError:
        return [], l


def chunked(l: List[T], chunk_size: int) -> Iterator[List[T]]:
    for i in range(0, len(l), chunk_size):
        yield l[i:i + chunk_size]


def sanitize_filename(filename: str, replace_to: str = '') -> str:
    excepted_chars = list(r':;/\?|*<>.')
    for char in excepted_chars:
        filename = filename.replace(char, replace_to)
    return filename


def method_dispatch(func: Callable[..., T]) -> Callable[..., T]:
    """
    Single-dispatch class method decorator
    Works like functools.singledispatch for none-static class methods.
    """
    dispatcher = functools.singledispatch(func)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return dispatcher.dispatch(args[1].__class__)(*args, **kwargs)

    # issue: https://github.com/python/mypy/issues/708
    wrapper.register = dispatcher.register  # type: ignore
    return wrapper


def const_generator(value: int) -> Generator[int, int, None]:
    while True:
        yield value


def delay_generator(maximum: int, step: int) -> Generator[int, int, None]:
    while True:
        yield from range(step, maximum, step)
        yield from const_generator(maximum)
