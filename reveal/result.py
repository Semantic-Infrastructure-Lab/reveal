"""Result type for explicit, type-safe error handling.

This module provides a Result type that replaces the inconsistent mix of:
- Returning None for errors
- Raising exceptions
- Returning error dicts

Example:
    >>> from reveal.result import Result, Success, Failure
    >>>
    >>> def divide(a: int, b: int) -> Result[float, str]:
    ...     if b == 0:
    ...         return Failure("Cannot divide by zero")
    ...     return Success(a / b)
    >>>
    >>> result = divide(10, 2)
    >>> if result.is_success():
    ...     print(f"Result: {result.value}")
    ... else:
    ...     print(f"Error: {result.error}")
"""

from typing import Generic, TypeVar, Union, Callable, List, Optional, NoReturn
from dataclasses import dataclass

T = TypeVar('T')
E = TypeVar('E')
U = TypeVar('U')


@dataclass
class Success(Generic[T]):
    """Successful result containing a value."""
    value: T

    def is_success(self) -> bool:
        """Check if this is a successful result."""
        return True

    def is_failure(self) -> bool:
        """Check if this is a failed result."""
        return False

    def unwrap(self) -> T:
        """Get the success value."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Get the success value or a default."""
        return self.value

    def map(self, f: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the success value."""
        return Success(f(self.value))

    def map_error(self, f: Callable[[E], E]) -> 'Result[T, E]':
        """Transform the error (no-op for Success)."""
        return self


@dataclass
class Failure(Generic[E]):
    """Failed result containing an error.

    Attributes:
        error: The error message or object
        details: Optional detailed error information
        suggestions: Optional list of actionable suggestions
        context: Optional context dictionary for debugging
    """
    error: E
    details: Optional[str] = None
    suggestions: Optional[List[str]] = None
    context: Optional[dict] = None

    def is_success(self) -> bool:
        """Check if this is a successful result."""
        return False

    def is_failure(self) -> bool:
        """Check if this is a failed result."""
        return True

    def unwrap(self) -> NoReturn:
        """Get the success value (raises for Failure)."""
        raise ValueError(f"Called unwrap() on Failure: {self.error}")

    def unwrap_or(self, default: T) -> T:
        """Get the success value or a default."""
        return default

    def map(self, f: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the success value (no-op for Failure)."""
        return self

    def map_error(self, f: Callable[[E], E]) -> 'Result[T, E]':
        """Transform the error."""
        return Failure(
            error=f(self.error),
            details=self.details,
            suggestions=self.suggestions,
            context=self.context
        )

    def __str__(self) -> str:
        """Format error with details and suggestions."""
        parts = [f"Error: {self.error}"]

        if self.details:
            parts.append(f"\nDetails: {self.details}")

        if self.suggestions:
            parts.append("\nSuggestions:")
            for suggestion in self.suggestions:
                parts.append(f"  - {suggestion}")

        if self.context:
            parts.append("\nContext:")
            for key, value in self.context.items():
                parts.append(f"  {key}: {value}")

        return "".join(parts)


# Type alias for Result
Result = Union[Success[T], Failure[E]]


# Convenience functions
def success(value: T) -> Success[T]:
    """Create a successful result."""
    return Success(value)


def failure(
    error: E,
    details: Optional[str] = None,
    suggestions: Optional[List[str]] = None,
    context: Optional[dict] = None
) -> Failure[E]:
    """Create a failed result with optional details and suggestions."""
    return Failure(
        error=error,
        details=details,
        suggestions=suggestions,
        context=context
    )


def from_optional(value: Optional[T], error: E) -> Result[T, E]:
    """Convert Optional to Result."""
    if value is None:
        return Failure(error)
    return Success(value)


def from_exception(f: Callable[[], T], error_map: Optional[Callable[[Exception], E]] = None) -> Result[T, E]:
    """Execute function and convert exception to Result.

    Args:
        f: Function to execute
        error_map: Optional function to transform exception into error type

    Returns:
        Success with function result, or Failure with mapped exception
    """
    try:
        return Success(f())
    except Exception as e:
        if error_map:
            return Failure(error_map(e))
        return Failure(str(e))  # type: ignore[arg-type]
