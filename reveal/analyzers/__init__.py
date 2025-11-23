"""Analyzers for different file types."""

from .base import BaseAnalyzer
from .yaml_analyzer import YAMLAnalyzer
from .json_analyzer import JSONAnalyzer
from .toml_analyzer import TOMLAnalyzer
from .markdown_analyzer import MarkdownAnalyzer
from .python_analyzer import PythonAnalyzer
from .sql_analyzer import SQLAnalyzer
from .text_analyzer import TextAnalyzer
from .gdscript_analyzer import GDScriptAnalyzer

# Tree-sitter based analyzers (optional dependency)
try:
    from .treesitter_base import TreeSitterAnalyzer
    from .rust_analyzer import RustAnalyzer
    from .csharp_analyzer import CSharpAnalyzer
    TREESITTER_ANALYZERS = ['TreeSitterAnalyzer', 'RustAnalyzer', 'CSharpAnalyzer']
except ImportError:
    TREESITTER_ANALYZERS = []

__all__ = [
    'BaseAnalyzer',
    'YAMLAnalyzer',
    'JSONAnalyzer',
    'TOMLAnalyzer',
    'MarkdownAnalyzer',
    'PythonAnalyzer',
    'SQLAnalyzer',
    'TextAnalyzer',
    'GDScriptAnalyzer',
] + TREESITTER_ANALYZERS
