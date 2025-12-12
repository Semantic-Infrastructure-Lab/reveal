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
from .jsonl import JsonlAnalyzer
from .gdscript import GDScriptAnalyzer
from .jupyter_analyzer import JupyterAnalyzer
from .javascript import JavaScriptAnalyzer
from .typescript import TypeScriptAnalyzer
from .bash import BashAnalyzer
from .nginx import NginxAnalyzer
from .toml import TomlAnalyzer
from .dockerfile import DockerfileAnalyzer

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
    # Office documents
    'DocxAnalyzer',
    'XlsxAnalyzer',
    'PptxAnalyzer',
    'OdtAnalyzer',
    'OdsAnalyzer',
    'OdpAnalyzer',
]
