"""Rendering package for reveal URI adapters.

This package contains renderers that display data fetched by adapters.
Each adapter type has its own renderer module that handles output formatting.
"""

from .adapters.reveal import render_reveal_structure
from .adapters.json_adapter import render_json_result
from .adapters.env import render_env_structure, render_env_variable
from .adapters.ast import render_ast_structure
from .adapters.help import render_help
from .adapters.python import render_python_structure, render_python_element

__all__ = [
    'render_reveal_structure',
    'render_json_result',
    'render_env_structure',
    'render_env_variable',
    'render_ast_structure',
    'render_help',
    'render_python_structure',
    'render_python_element',
]
