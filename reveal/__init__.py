"""Reveal - Explore code semantically.

A clean, simple tool for progressive code exploration.
"""

# Version is read from pyproject.toml at runtime
try:
    from importlib.metadata import version
    __version__ = version("reveal-cli")
except Exception:
    # Fallback for development/editable installs
    __version__ = "0.41.0-dev"

# Import base classes for external use
from .base import FileAnalyzer
from .registry import register, get_analyzer, get_all_analyzers
from .treesitter import TreeSitterAnalyzer

# Import all built-in analyzers to register them
from .analyzers import *  # noqa: F401, F403

# Import type definitions to auto-register them in TypeRegistry
from .schemas import python  # noqa: F401

__all__ = [
    'FileAnalyzer',
    'TreeSitterAnalyzer',
    'register',
    'get_analyzer',
    'get_all_analyzers',
]
