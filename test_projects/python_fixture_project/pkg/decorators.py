from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def trace_call(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        return func(*args, **kwargs)

    return wrapper
