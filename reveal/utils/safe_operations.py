"""Safe operation utilities for graceful error handling.

Provides decorators and context managers for operations that should
fail gracefully without propagating exceptions.
"""

import functools
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_operation(
    fallback: Optional[T] = None,
    log_level: int = logging.DEBUG,
    exceptions: tuple = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for operations that should fail gracefully.

    Catches exceptions and returns a fallback value instead of raising.
    Useful for optional enhancements that shouldn't break core functionality.

    Args:
        fallback: Value to return on exception (default: None)
        log_level: Logging level for caught exceptions (default: DEBUG)
        exceptions: Tuple of exception types to catch (default: all)

    Returns:
        Decorated function that returns fallback on error

    Example:
        @safe_operation(fallback=[])
        def get_optional_metadata(path):
            # If this fails, empty list is returned
            return parse_metadata(path)

        @safe_operation(fallback=None, log_level=logging.WARNING)
        def load_optional_config():
            return json.load(open('config.json'))
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.log(
                    log_level,
                    f"{func.__name__} failed gracefully: {e}"
                )
                return fallback  # type: ignore[return-value]
        return wrapper
    return decorator


def safe_read_file(
    path: str,
    fallback: str = "",
    encoding: str = "utf-8"
) -> str:
    """Safely read a file, returning fallback on any error.

    Args:
        path: Path to file
        fallback: Value to return on error (default: empty string)
        encoding: File encoding (default: utf-8)

    Returns:
        File contents or fallback value
    """
    try:
        with open(path, encoding=encoding) as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Failed to read {path}: {e}")
        return fallback


def safe_json_loads(
    content: str,
    fallback: Optional[Any] = None
) -> Any:
    """Safely parse JSON, returning fallback on error.

    Args:
        content: JSON string
        fallback: Value to return on parse error (default: None)

    Returns:
        Parsed JSON or fallback value
    """
    import json
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"JSON parse failed: {e}")
        return fallback


def safe_yaml_loads(
    content: str,
    fallback: Optional[Any] = None
) -> Any:
    """Safely parse YAML, returning fallback on error.

    Args:
        content: YAML string
        fallback: Value to return on parse error (default: None)

    Returns:
        Parsed YAML or fallback value
    """
    try:
        import yaml
        return yaml.safe_load(content)
    except Exception as e:
        logger.debug(f"YAML parse failed: {e}")
        return fallback


class SafeContext:
    """Context manager for safe operations with automatic cleanup.

    Example:
        with SafeContext() as ctx:
            result = risky_operation()
            ctx.value = result

        # ctx.value is None if exception occurred
        if ctx.value:
            use_result(ctx.value)
    """

    def __init__(self, fallback: Any = None, log_level: int = logging.DEBUG):
        self.fallback = fallback
        self.log_level = log_level
        self.value = fallback
        self.exception: Optional[Exception] = None

    def __enter__(self) -> "SafeContext":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            logger.log(self.log_level, f"SafeContext caught: {exc_val}")
            self.exception = exc_val
            self.value = self.fallback
            return True  # Suppress exception
        return False
