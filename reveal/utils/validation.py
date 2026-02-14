"""Validation utilities for common patterns.

This module provides reusable validation functions that eliminate ~60 lines
of ad-hoc validation code across 10+ adapters and modules.

Common patterns consolidated:
    - Path existence checking (if not path.exists(): raise FileNotFoundError)
    - File vs directory validation
    - Port number validation
    - Package import checking
    - Parameter type validation

Usage:
    # Path validation
    config_file = require_file(Path('config.yaml'))
    data_dir = require_directory(Path('data/'))

    # With custom error messages
    require_path_exists(path, "Configuration file")

    # Package checking
    require_package('pymysql', 'pip install pymysql')

    # Port validation
    port = validate_port(3306, name='MySQL port')
"""

from pathlib import Path
from typing import Optional, Any, Callable


def require_path_exists(
    path: Path,
    path_type: Optional[str] = None
) -> Path:
    """Validate that a path exists.

    Args:
        path: Path to check
        path_type: Description for error message (e.g., "Configuration file", "Data directory")

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If path does not exist

    Examples:
        >>> config = require_path_exists(Path('config.yaml'))
        >>> data_dir = require_path_exists(Path('data/'), "Data directory")
    """
    if not path.exists():
        type_desc = path_type or "Path"
        raise FileNotFoundError(f"{type_desc} not found: {path}")
    return path


def require_file(
    path: Path,
    file_type: Optional[str] = None
) -> Path:
    """Validate that a path exists and is a file.

    Args:
        path: Path to check
        file_type: Description for error message (e.g., "Configuration file")

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If path does not exist
        ValueError: If path exists but is not a file

    Examples:
        >>> config = require_file(Path('config.yaml'))
        >>> data = require_file(Path('data.json'), "Data file")
    """
    type_desc = file_type or "File"
    require_path_exists(path, type_desc)

    if not path.is_file():
        raise ValueError(f"{type_desc} is not a file: {path}")

    return path


def require_directory(
    path: Path,
    dir_type: Optional[str] = None
) -> Path:
    """Validate that a path exists and is a directory.

    Args:
        path: Path to check
        dir_type: Description for error message (e.g., "Data directory")

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If path does not exist
        ValueError: If path exists but is not a directory

    Examples:
        >>> data_dir = require_directory(Path('data/'))
        >>> src = require_directory(Path('src/'), "Source directory")
    """
    type_desc = dir_type or "Directory"
    require_path_exists(path, type_desc)

    if not path.is_dir():
        raise ValueError(f"{type_desc} is not a directory: {path}")

    return path


def validate_port(
    port: int,
    port_range: tuple[int, int] = (1, 65535),
    name: Optional[str] = None
) -> int:
    """Validate that a port number is in valid range.

    Args:
        port: Port number to validate
        port_range: Tuple of (min_port, max_port), default (1, 65535)
        name: Port name for error message (e.g., "MySQL port")

    Returns:
        The port number (for chaining)

    Raises:
        ValueError: If port is outside valid range

    Examples:
        >>> port = validate_port(3306)
        >>> port = validate_port(8080, name="HTTP port")
        >>> port = validate_port(5000, port_range=(1024, 49151), name="Unprivileged port")
    """
    min_port, max_port = port_range

    if not isinstance(port, int):
        port_name = name or "Port"
        raise TypeError(f"{port_name} must be an integer, got {type(port).__name__}")

    if not (min_port <= port <= max_port):
        port_name = name or "Port"
        raise ValueError(
            f"{port_name} must be between {min_port} and {max_port}, got {port}"
        )

    return port


def require_package(
    package_name: str,
    install_command: str,
    import_name: Optional[str] = None
) -> None:
    """Validate that a required package is installed.

    Args:
        package_name: Package name (for error message)
        install_command: Command to install the package
        import_name: Name to import (if different from package_name)

    Raises:
        ImportError: If package is not installed

    Examples:
        >>> require_package('pymysql', 'pip install pymysql')
        >>> require_package('tree-sitter', 'pip install tree-sitter', import_name='tree_sitter')
    """
    module_name = import_name or package_name

    try:
        __import__(module_name)
    except ImportError:
        raise ImportError(
            f"{package_name} is required but not installed.\n\n"
            f"Install with: {install_command}"
        )


def require_type(
    value: Any,
    expected_type: type,
    param_name: str
) -> Any:
    """Validate parameter type.

    Args:
        value: Value to check
        expected_type: Expected type
        param_name: Parameter name for error message

    Returns:
        The value (for chaining)

    Raises:
        TypeError: If value is not of expected type

    Examples:
        >>> limit = require_type(10, int, 'limit')
        >>> name = require_type('test', str, 'name')
    """
    if not isinstance(value, expected_type):
        raise TypeError(
            f"{param_name} must be {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def require_non_empty(
    value: str,
    param_name: str
) -> str:
    """Validate that a string parameter is non-empty.

    Args:
        value: String to check
        param_name: Parameter name for error message

    Returns:
        The value (for chaining)

    Raises:
        ValueError: If string is empty or whitespace-only

    Examples:
        >>> query = require_non_empty('SELECT * FROM users', 'query')
        >>> require_non_empty('', 'name')  # Raises ValueError
    """
    if not value or not value.strip():
        raise ValueError(f"{param_name} cannot be empty")
    return value


def validate_range(
    value: float,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    param_name: Optional[str] = None
) -> float:
    """Validate that a numeric value is within a range.

    Args:
        value: Value to check
        min_value: Minimum allowed value (None = no minimum)
        max_value: Maximum allowed value (None = no maximum)
        param_name: Parameter name for error message

    Returns:
        The value (for chaining)

    Raises:
        ValueError: If value is outside the range

    Examples:
        >>> confidence = validate_range(0.95, 0.0, 1.0, 'confidence')
        >>> validate_range(1.5, 0.0, 1.0, 'probability')  # Raises ValueError
        >>> age = validate_range(25, min_value=0, param_name='age')
    """
    name = param_name or "Value"

    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {value}")

    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value}, got {value}")

    return value


def validate_one_of(
    value: Any,
    allowed_values: list,
    param_name: Optional[str] = None
) -> Any:
    """Validate that a value is one of the allowed values.

    Args:
        value: Value to check
        allowed_values: List of allowed values
        param_name: Parameter name for error message

    Returns:
        The value (for chaining)

    Raises:
        ValueError: If value is not in allowed_values

    Examples:
        >>> mode = validate_one_of('production', ['development', 'staging', 'production'], 'mode')
        >>> validate_one_of('invalid', ['a', 'b', 'c'], 'option')  # Raises ValueError
    """
    if value not in allowed_values:
        name = param_name or "Value"
        allowed = ', '.join(repr(v) for v in allowed_values)
        raise ValueError(f"{name} must be one of [{allowed}], got {repr(value)}")

    return value


def validate_callable(
    value: Any,
    param_name: str
) -> Callable:
    """Validate that a value is callable.

    Args:
        value: Value to check
        param_name: Parameter name for error message

    Returns:
        The value (for chaining)

    Raises:
        TypeError: If value is not callable

    Examples:
        >>> callback = validate_callable(lambda x: x * 2, 'callback')
        >>> validate_callable('not_callable', 'handler')  # Raises TypeError
    """
    if not callable(value):
        raise TypeError(f"{param_name} must be callable, got {type(value).__name__}")
    return value


# Convenience validators for common patterns
def require_readable_file(path: Path, file_type: Optional[str] = None) -> Path:
    """Validate that a file exists and is readable.

    Args:
        path: Path to check
        file_type: Description for error message

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If path is not a file
        PermissionError: If file is not readable
    """
    require_file(path, file_type)

    # Check read permission
    try:
        with open(path, 'r') as f:
            pass
    except PermissionError:
        type_desc = file_type or "File"
        raise PermissionError(f"{type_desc} is not readable: {path}")

    return path


def require_writable_directory(path: Path, dir_type: Optional[str] = None) -> Path:
    """Validate that a directory exists and is writable.

    Args:
        path: Path to check
        dir_type: Description for error message

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If directory does not exist
        ValueError: If path is not a directory
        PermissionError: If directory is not writable
    """
    require_directory(path, dir_type)

    # Check write permission by attempting to create a temp file
    import tempfile
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
    except PermissionError:
        type_desc = dir_type or "Directory"
        raise PermissionError(f"{type_desc} is not writable: {path}")

    return path
