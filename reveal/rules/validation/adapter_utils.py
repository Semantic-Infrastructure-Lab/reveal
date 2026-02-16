"""Adapter-related utilities for validation rules.

Consolidates adapter access and discovery logic used across multiple validation
rules (V016, V018, V019, V020) to reduce duplication and improve maintainability.
"""

from pathlib import Path
from typing import Optional, List, Tuple


def find_adapter_file(reveal_root: Path, scheme: str) -> Optional[Path]:
    """Find the adapter file for a given scheme.

    Searches for adapter files following reveal's naming conventions:
    1. adapters/<scheme>.py (e.g., adapters/env.py)
    2. adapters/<scheme>_adapter.py (e.g., adapters/json_adapter.py)
    3. adapters/<scheme>/adapter.py (e.g., adapters/git/adapter.py)
    4. adapters/<scheme>/__init__.py (e.g., adapters/mysql/__init__.py)

    Args:
        reveal_root: Path to reveal package root
        scheme: URI scheme (e.g., 'env', 'ast', 'git')

    Returns:
        Path to adapter file, or None if not found

    Example:
        >>> reveal_root = Path("reveal")
        >>> adapter_file = find_adapter_file(reveal_root, "git")
        >>> print(adapter_file)  # reveal/adapters/git/adapter.py
    """
    adapters_dir = reveal_root / 'adapters'
    if not adapters_dir.exists():
        return None

    # Try common patterns in order of preference
    patterns = [
        f"{scheme}.py",                    # 1. Direct file
        f"{scheme}_adapter.py",            # 2. Named adapter file
        f"{scheme}/adapter.py",            # 3. Package with adapter.py
        f"{scheme}/__init__.py"            # 4. Package __init__
    ]

    for pattern in patterns:
        adapter_file = adapters_dir / pattern
        if adapter_file.exists():
            return adapter_file

    return None


def get_adapter_schemes() -> List[str]:
    """Get list of all registered adapter schemes.

    Returns:
        List of URI schemes (e.g., ['env', 'ast', 'git', ...])

    Example:
        >>> schemes = get_adapter_schemes()
        >>> print(len(schemes))  # 13
        >>> print('git' in schemes)  # True
    """
    try:
        from ...adapters.base import list_supported_schemes
        return sorted(list_supported_schemes())
    except Exception:
        return []


def get_adapter_class(scheme: str):
    """Get adapter class for given scheme.

    Args:
        scheme: URI scheme (e.g., 'git', 'env')

    Returns:
        Adapter class or None if not found

    Example:
        >>> adapter_class = get_adapter_class('git')
        >>> print(adapter_class.__name__)  # GitAdapter
    """
    try:
        from ...adapters.base import get_adapter_class as _get_adapter_class
        return _get_adapter_class(scheme)
    except Exception:
        return None


def get_renderer_class(scheme: str):
    """Get renderer class for given scheme.

    Args:
        scheme: URI scheme (e.g., 'git', 'env')

    Returns:
        Renderer class or None if not found

    Example:
        >>> renderer = get_renderer_class('git')
        >>> print(hasattr(renderer, 'render_structure'))  # True
    """
    try:
        from ...adapters.base import get_renderer_class as _get_renderer_class
        return _get_renderer_class(scheme)
    except Exception:
        return None


def get_adapter_and_renderer(scheme: str) -> Tuple[Optional[type], Optional[type]]:
    """Get both adapter and renderer classes for a scheme.

    Args:
        scheme: URI scheme (e.g., 'git', 'env')

    Returns:
        Tuple of (adapter_class, renderer_class), either may be None

    Example:
        >>> adapter_class, renderer_class = get_adapter_and_renderer('git')
        >>> if adapter_class and renderer_class:
        ...     print("Both registered correctly")
    """
    return get_adapter_class(scheme), get_renderer_class(scheme)


def find_class_definition_line(file_path: Path, class_name: str) -> int:
    """Find line number where class is defined.

    Args:
        file_path: Path to Python file
        class_name: Name of class to find

    Returns:
        Line number (1-indexed) or 1 if not found

    Example:
        >>> line = find_class_definition_line(Path("adapter.py"), "GitAdapter")
        >>> print(f"GitAdapter defined at line {line}")
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, start=1):
                if f'class {class_name}' in line:
                    return i
    except Exception:
        pass
    return 1


def find_method_definition_line(file_path: Path, method_name: str) -> int:
    """Find line number where method is defined.

    Args:
        file_path: Path to Python file
        method_name: Name of method to find (e.g., '__init__', 'get_element')

    Returns:
        Line number (1-indexed) or 1 if not found

    Example:
        >>> line = find_method_definition_line(Path("adapter.py"), "get_element")
        >>> print(f"get_element defined at line {line}")
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, start=1):
                if f'def {method_name}' in line:
                    return i
    except Exception:
        pass
    return 1


def find_init_definition_line(file_path: Path) -> int:
    """Find line number where __init__ method is defined.

    Convenience wrapper around find_method_definition_line for __init__.

    Args:
        file_path: Path to Python file

    Returns:
        Line number (1-indexed) or 1 if not found

    Example:
        >>> line = find_init_definition_line(Path("adapter.py"))
        >>> print(f"__init__ defined at line {line}")
    """
    return find_method_definition_line(file_path, '__init__')
