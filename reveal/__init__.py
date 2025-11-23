"""Reveal - Explore code semantically.

A clean, simple tool for progressive code exploration.
"""

__version__ = "0.2.0"

# Import base classes for external use
from .base import FileAnalyzer, register, get_analyzer
from .treesitter import TreeSitterAnalyzer

# Import all built-in analyzers to register them
from .analyzers_new import *

__all__ = [
    'FileAnalyzer',
    'TreeSitterAnalyzer',
    'register',
    'get_analyzer',
]
