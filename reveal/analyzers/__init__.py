"""Built-in analyzers for reveal.

This package contains reference implementations showing how easy it is
to add new file type support.

Each analyzer is typically 10-20 lines of code!
"""

# Import all analyzers to register them
from .python import PythonAnalyzer
from .rust import RustAnalyzer
from .go import GoAnalyzer
from .c import CAnalyzer
from .cpp import CppAnalyzer
from .java import JavaAnalyzer
from .php import PhpAnalyzer
from .ruby import RubyAnalyzer
from .lua import LuaAnalyzer
from .csharp import CSharpAnalyzer
from .scala import ScalaAnalyzer
from .sql import SQLAnalyzer
from .markdown import MarkdownAnalyzer
from .yaml_json import YamlAnalyzer, JsonAnalyzer
from .jsonl import JsonlAnalyzer
from .gdscript import GDScriptAnalyzer
from .jupyter_analyzer import JupyterAnalyzer
from .javascript import JavaScriptAnalyzer
from .typescript import TypeScriptAnalyzer
from .bash import BashAnalyzer
from .nginx import NginxAnalyzer
from .toml import TomlAnalyzer
from .dockerfile import DockerfileAnalyzer
from .html import HTMLAnalyzer

# Office document analyzers (ZIP+XML based)
from .office import (
    DocxAnalyzer,
    XlsxAnalyzer,
    PptxAnalyzer,
    OdtAnalyzer,
    OdsAnalyzer,
    OdpAnalyzer,
)

__all__ = [
    'PythonAnalyzer',
    'RustAnalyzer',
    'GoAnalyzer',
    'CAnalyzer',
    'CppAnalyzer',
    'JavaAnalyzer',
    'PhpAnalyzer',
    'RubyAnalyzer',
    'LuaAnalyzer',
    'CSharpAnalyzer',
    'ScalaAnalyzer',
    'SQLAnalyzer',
    'MarkdownAnalyzer',
    'YamlAnalyzer',
    'JsonAnalyzer',
    'JsonlAnalyzer',
    'GDScriptAnalyzer',
    'JupyterAnalyzer',
    'JavaScriptAnalyzer',
    'TypeScriptAnalyzer',
    'BashAnalyzer',
    'NginxAnalyzer',
    'TomlAnalyzer',
    'DockerfileAnalyzer',
    'HTMLAnalyzer',
    # Office documents
    'DocxAnalyzer',
    'XlsxAnalyzer',
    'PptxAnalyzer',
    'OdtAnalyzer',
    'OdsAnalyzer',
    'OdpAnalyzer',
]
