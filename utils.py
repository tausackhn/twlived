import functools
from typing import List, Tuple, Callable, Any, TypeVar

T = TypeVar('T')


def split_by(l: List[T], element: T) -> Tuple[List[T], List[T]]:
    try:
        element_index = l.index(element)
        return l[:element_index], l[element_index + 1:]
    except ValueError:
        return [], l


def chunked(l: List[T], chunk_size: int) -> List[List[T]]:
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
    def wrapper(*args: Any, **_: Any) -> T:
        return dispatcher.dispatch(args[1].__class__)(*args, **_)

    # issue: https://github.com/python/mypy/issues/708
    wrapper.register = dispatcher.register  # type: ignore
    return wrapper
