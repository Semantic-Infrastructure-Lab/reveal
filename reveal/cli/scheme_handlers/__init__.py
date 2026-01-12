"""CLI handlers for different URI schemes.

Each handler module provides a handle_<scheme>() function that processes
URIs for that scheme (e.g., env://, ast://, mysql://, etc.).

Extracting handlers from routing.py reduces complexity:
- routing.py: C58 → <10 (dispatcher only)
- handlers: Isolated, testable modules
"""

from .env import handle_env
from .ast import handle_ast
from .help import handle_help
from .python import handle_python
from .json import handle_json
from .reveal import handle_reveal
from .stats import handle_stats
from .mysql import handle_mysql
from .sqlite import handle_sqlite
from .imports import handle_imports
from .diff import handle_diff
from .markdown import handle_markdown

__all__ = [
    'handle_env',
    'handle_ast',
    'handle_help',
    'handle_python',
    'handle_json',
    'handle_reveal',
    'handle_stats',
    'handle_mysql',
    'handle_sqlite',
    'handle_imports',
    'handle_diff',
    'handle_markdown',
]
