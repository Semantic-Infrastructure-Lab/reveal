"""Adapter-specific renderers for reveal URI schemes.

Each module handles rendering for a specific URI adapter:
- reveal.py: reveal:// internal structure
- json_adapter.py: json:// navigation
- env.py: env:// environment variables
- ast.py: ast:// code queries
- help.py: help:// documentation
- python.py: python:// runtime inspection
- markdown_query.py: markdown:// frontmatter queries
"""

from .reveal import render_reveal_structure
from .json_adapter import render_json_result
from .env import render_env_structure, render_env_variable
from .ast import render_ast_structure
from .help import render_help
from .python import render_python_structure, render_python_element
from .markdown_query import render_markdown_query

__all__ = [
    'render_reveal_structure',
    'render_json_result',
    'render_env_structure',
    'render_env_variable',
    'render_ast_structure',
    'render_help',
    'render_python_structure',
    'render_python_element',
    'render_markdown_query',
]
