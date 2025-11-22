"""Progressive Reveal CLI - A tool for exploring files at different levels of detail."""

__version__ = "0.1.0"
__author__ = "Progressive Reveal Team"

# Export registry functions for plugin development
from .registry import register, get_analyzer, list_analyzers, list_extensions

__all__ = [
    'register',
    'get_analyzer',
    'list_analyzers',
    'list_extensions',
    '__version__',
]
