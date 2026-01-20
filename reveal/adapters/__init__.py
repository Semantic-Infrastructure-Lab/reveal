"""URI adapters for exploring non-file resources."""

from .base import (
    ResourceAdapter,
    register_adapter,
    register_renderer,
    get_adapter_class,
    get_renderer_class,
    list_supported_schemes,
    list_renderer_schemes,
)

from .env import EnvAdapter
from .ast import AstAdapter
from .claude import ClaudeAdapter
from .diff import DiffAdapter
from .help import HelpAdapter
from .imports import ImportsAdapter
from .json_adapter import JsonAdapter
from .markdown import MarkdownQueryAdapter
from .mysql import MySQLAdapter
from .python import PythonAdapter
from .reveal import RevealAdapter
from .sqlite import SQLiteAdapter
from .ssl import SSLAdapter
from .stats import StatsAdapter

# Optional adapters (require extra dependencies)
try:
    from .git import GitAdapter
    _git_available = True
except ImportError:
    _git_available = False
    GitAdapter = None

__all__ = [
    # Base classes and registry functions
    'ResourceAdapter',
    'register_adapter',
    'register_renderer',
    'get_adapter_class',
    'get_renderer_class',
    'list_supported_schemes',
    'list_renderer_schemes',
    # Adapter classes
    'EnvAdapter',
    'AstAdapter',
    'ClaudeAdapter',
    'DiffAdapter',
    'HelpAdapter',
    'ImportsAdapter',
    'JsonAdapter',
    'MarkdownQueryAdapter',
    'MySQLAdapter',
    'PythonAdapter',
    'RevealAdapter',
    'SQLiteAdapter',
    'SSLAdapter',
    'StatsAdapter',
]
if _git_available:
    __all__.append('GitAdapter')
