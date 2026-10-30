from dataclasses import dataclass
from functools import wraps


@dataclass(frozen=True)
class Operation:
    name: str
    function: object
    mutating: bool


OPERATIONS: dict[str, Operation] = {}


def remote_operation(name: str, *, mutating: bool = False):
    """Register a strict API operation while preserving direct-mode calls."""

    def decorator(function):
        @wraps(function)
        def wrapper(session, *args, **kwargs):
            from shared.internal_api.client import RemoteSession

            if isinstance(session, RemoteSession):
                return session.call(name, args=args, kwargs=kwargs, mutating=mutating)

            return function(session, *args, **kwargs)

        if name in OPERATIONS:
            raise RuntimeError(f'Duplicate internal API operation: {name}')

        OPERATIONS[name] = Operation(name, wrapper, mutating)
        return wrapper

    return decorator
