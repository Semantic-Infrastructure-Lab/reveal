"""Built-in analyzers for reveal.

This package contains reference implementations showing how easy it is
to add new file type support.

Each analyzer is typically 10-20 lines of code!
"""

# Import all analyzers to register them
from .python import PythonAnalyzer
from .rust import RustAnalyzer
from .go import GoAnalyzer
from .markdown import MarkdownAnalyzer
from .yaml_json import YamlAnalyzer, JsonAnalyzer

__all__ = [
    'PythonAnalyzer',
    'RustAnalyzer',
    'GoAnalyzer',
    'MarkdownAnalyzer',
    'YamlAnalyzer',
    'JsonAnalyzer',
]
